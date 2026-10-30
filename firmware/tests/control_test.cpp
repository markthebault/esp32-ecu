#include "ecu/control.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

#define CHECK(x) do { if (!(x)) { std::cerr << __LINE__ << ": " << #x << '\n'; std::abort(); } } while (false)

static std::uint64_t wheel(ecu::MissingTooth& d, std::uint64_t t, unsigned slots,
                           unsigned missing, unsigned period, unsigned revolutions) {
    for (unsigned rev=0; rev<revolutions; ++rev) {
        for (unsigned i=0; i<slots-missing; ++i) {
            t += period;
            d.edge(t);
        }
        t += missing*period;
    }
    return t;
}

static ecu::Sensors good() { return {45,15,85,25,1,13.8,5,10000,true,true}; }

int main() {
    unsigned cases = 0;
    for (auto config : {ecu::MissingTooth::Config{60,2,8000}, {36,1,8000}}) {
        for (unsigned rpm : {80U,200U,1000U,4000U,7500U}) {
            ecu::MissingTooth d(config);
            const auto period = static_cast<unsigned>(60000000ULL/(rpm*config.slots));
            auto t = wheel(d,0,config.slots,config.missing,period,5);
            CHECK(d.synced());
            CHECK(std::abs(d.rpm()-rpm)/rpm < .015);
            d.tick(t+200000);
            CHECK(!d.synced());
            ++cases;
        }
    }
    {
        ecu::MissingTooth d({60,2,8000});
        auto t = wheel(d,0,60,2,1000,4);
        CHECK(d.synced());
        d.edge(t+1); // Extra short edge loses sync, rather than generating spark.
        CHECK(!d.synced());
        t = wheel(d,t+1,60,2,1000,5);
        CHECK(d.synced());
        d.edge(t-5000); CHECK(!d.synced());
        CHECK(!ecu::MissingTooth({0,2,8000}).valid());
        ++cases;
    }
    {
        ecu::MissingTooth d({60,2,8000});
        std::uint64_t t=0;
        for (unsigned i=0;i<400;++i) { t+=1000; d.edge(t); }
        CHECK(!d.synced()); // Regular pulse train cannot masquerade as 60-2.
        t=wheel(d,t,60,2,1000,4);
        CHECK(d.synced());
        // Gap at wrong tooth count is rejected.
        d.edge(t+3000); CHECK(!d.synced());
        ++cases;
    }
    {
        ecu::Calibration c;
        auto s=good();
        CHECK(ecu::inhibit(c,s,1000,true,true,true,true,10000)==ecu::Fault::uncalibrated);
        c.vehicle_reviewed=true;
        CHECK(ecu::inhibit(c,s,1000,true,true,true,true,10000)==ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,1000,false,true,true,true,10000)!=ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,1000,true,false,true,true,10000)!=ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,1000,true,true,false,true,10000)!=ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,1000,true,true,true,false,10000)!=ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,1000,true,true,true,true,30001)!=ecu::Fault::none);
        CHECK(ecu::inhibit(c,s,6500,true,true,true,true,10000)!=ecu::Fault::none);
        s.lambda_ready=false;
        CHECK(ecu::inhibit(c,s,1000,true,true,true,true,10000)!=ecu::Fault::none);
        s=good(); s.clt_c=116;
        CHECK(ecu::inhibit(c,s,1000,true,true,true,true,10000)!=ecu::Fault::none);
        s=good(); s.map_kpa=std::numeric_limits<double>::quiet_NaN();
        CHECK(!ecu::plausible(s));
        c.injector_deadtime_ms=std::numeric_limits<double>::infinity();
        CHECK(!c.valid());
        ++cases;
    }
    {
        auto s=good();
        ecu::Calibration c;
        auto a=ecu::demand(c,s,1000,.8,10,1);
        CHECK(a.valid && a.pulse_ms>1 && a.pulse_ms<5);
        s.map_kpa=90;
        auto b=ecu::demand(c,s,1000,.8,10,1);
        CHECK(b.valid);
        CHECK(std::abs((b.pulse_ms-c.injector_deadtime_ms)/(a.pulse_ms-c.injector_deadtime_ms)-2)<1e-10);
        CHECK(!ecu::demand(c,s,6400,1.2,10,1).valid); // Injector capacity exceeded.
        CHECK(!ecu::demand(c,s,1000,.8,std::numeric_limits<double>::quiet_NaN(),1).valid);
        CHECK(!ecu::demand(c,s,1000,.8,10,1.2).valid);
        ++cases;
    }
    {
        ecu::LambdaTrim trim;
        auto s=good(); s.lambda=1.1;
        double v=1;
        for (unsigned i=0;i<10000;++i) v=trim.update(s,1000,.01);
        CHECK(v>1 && v<=1.1);
        s.lambda=.9;
        for (unsigned i=0;i<20000;++i) v=trim.update(s,1000,.01);
        CHECK(v>=.9 && v<1);
        s.lambda_ready=false;
        CHECK(trim.update(s,1000,.01)==1);
        ++cases;
    }
    {
        ecu::PulseQueue q;
        unsigned state=0;
        auto write=[&](unsigned ch,bool high) { if (high) state|=1U<<ch; else state&=~(1U<<ch); };
        CHECK(q.insert_pulse(0,1000,2000,0));
        CHECK(!q.insert_pulse(0,1500,1000,0));
        CHECK(q.insert_pulse(4,1000,1000,0));
        CHECK(q.dispatch(1000,write)); CHECK(state==17);
        CHECK(!q.insert_pulse(4,2500,1000,1000)); // Active-channel reservation.
        CHECK(q.dispatch(2000,write)); CHECK(state==1);
        CHECK(q.dispatch(3000,write)); CHECK(state==0);
        CHECK(q.insert_pulse(1,5000,1000,3000));
        CHECK(!q.dispatch(5026,write)); CHECK(state==0 && q.size()==0);
        CHECK(!q.insert_pulse(8,6000,1000,5000));
        CHECK(!q.insert_pulse(4,6000,4000,5000));
        CHECK(!q.insert_pulse(0,6000,16000,5000));
        CHECK(!q.insert_pulse(0,std::numeric_limits<std::uint64_t>::max()-100,1000,5000));
        CHECK(q.insert_pulse(2,6000,1000,5000));
        CHECK(!q.dispatch(3000,write)); CHECK(state==0 && q.size()==0);
        ++cases;
    }
    // Deterministic fault/noise sweep. A corrupted stream never leaves an
    // actuator on: the decoder only reports phase and the queue owns edges.
    for (unsigned seed=1;seed<=100;++seed) {
        ecu::MissingTooth d({60,2,8000});
        std::uint64_t t=0;
        std::uint32_t rng=seed;
        for (unsigned i=0;i<10000;++i) {
            rng=1664525*rng+1013904223;
            t+=1+rng%200000;
            d.edge(t);
            CHECK(std::isfinite(d.rpm()));
            CHECK(d.rpm()>=0 && d.rpm()<=8000);
        }
        ++cases;
    }
    std::cout << cases << " control scenarios passed\n";
}
