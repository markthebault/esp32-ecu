#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace ecu {

// Angles cover one crank revolution. This decoder alone does not establish
// the 720-degree phase needed for sequential injection or sequential ignition.
class MissingTooth {
public:
    struct Config { unsigned slots = 60; unsigned missing = 2; unsigned max_rpm = 8000; };
    explicit MissingTooth(Config c) : c_(c) {
        valid_ = c.slots >= 12 && c.slots <= 120 && c.missing >= 1 &&
                 c.missing <= 3 && c.missing < c.slots/4 &&
                 c.max_rpm >= 500 && c.max_rpm <= 12000;
    }
    bool edge(std::uint64_t us) {
        if (!valid_) return false;
        if (!seen_) { seen_ = true; last_ = us; return false; }
        if (us <= last_) { reset(); return false; }
        const auto dt = us-last_;
        last_ = us;
        const auto minimum = 60000000ULL / (c_.max_rpm*c_.slots);
        if (dt < minimum || dt > 150000) { lose(); return false; }
        if (period_ == 0) { period_ = static_cast<double>(dt); return false; }
        const auto ratio = dt/period_;
        if (ratio >= (c_.missing+1)*.8 && ratio <= (c_.missing+1)*1.2) {
            if (gap_seen_ && teeth_ != c_.slots-c_.missing-1) {
                lose(); return false;
            }
            gap_seen_ = true;
            teeth_ = 0;
            if (gaps_ < 2) ++gaps_;
            synced_ = gaps_ >= 2;
            // A gap interval averages several tooth periods, so use it only
            // after geometry checks and avoid accumulating missing teeth.
            period_ = static_cast<double>(dt)/(c_.missing+1);
            return synced_;
        }
        if (ratio < .65 || ratio > 1.4) { lose(); return false; }
        period_ = .75*period_+.25*static_cast<double>(dt);
        ++teeth_;
        if (teeth_ > c_.slots-c_.missing-1 && gap_seen_) lose();
        return false;
    }
    void tick(std::uint64_t now) {
        if (seen_ && (now < last_ || now-last_ > stall_timeout())) reset();
    }
    void reset() { seen_ = false; last_ = 0; lose(); }
    bool synced() const { return synced_; }
    bool valid() const { return valid_; }
    double rpm() const { return period_ > 0 && synced_ ? 60000000.0/(period_*c_.slots) : 0; }
    unsigned tooth() const { return teeth_; }
    std::uint64_t stall_timeout() const {
        return static_cast<std::uint64_t>(std::clamp(period_*(c_.missing+2)*2, 20000.0, 150000.0));
    }
private:
    void lose() { synced_ = false; gap_seen_ = false; gaps_ = 0; teeth_ = 0; period_ = 0; }
    Config c_;
    bool valid_ = false, seen_ = false, synced_ = false, gap_seen_ = false;
    unsigned teeth_ = 0, gaps_ = 0;
    std::uint64_t last_ = 0;
    double period_ = 0;
};

struct Sensors {
    double map_kpa = 0, tps_percent = 0, clt_c = 0, iat_c = 0;
    double lambda = 0, battery_v = 0, sensor_v = 0;
    std::uint64_t sampled_us = 0;
    bool valid = false, lambda_ready = false;
};

struct Calibration {
    // Illustrative constants, not an engine tune. Activation requires a
    // reviewed engine profile and a separate target timing implementation.
    double displacement_cc = 2000;
    unsigned cylinders = 4;
    double injector_cc_min = 250;
    double fuel_density_g_cc = .745;
    double stoich_afr = 14.7;
    double injector_deadtime_ms = 1.0;
    double max_dwell_ms = 3.0;
    double max_duty = .75;
    double rpm_limit = 6500;
    bool vehicle_reviewed = false;
    bool valid() const {
        const std::array<double, 9> values{displacement_cc, injector_cc_min, fuel_density_g_cc,
            stoich_afr, injector_deadtime_ms, max_dwell_ms, max_duty, rpm_limit, static_cast<double>(cylinders)};
        for (auto x : values) if (!std::isfinite(x)) return false;
        return cylinders == 4 && displacement_cc >= 500 && displacement_cc <= 4000 &&
            injector_cc_min >= 100 && injector_cc_min <= 1000 &&
            fuel_density_g_cc >= .6 && fuel_density_g_cc <= .9 && stoich_afr >= 9 && stoich_afr <= 16 &&
            injector_deadtime_ms >= .1 && injector_deadtime_ms <= 2.5 &&
            max_dwell_ms >= .5 && max_dwell_ms <= 3.5 && max_duty > 0 && max_duty <= .8 &&
            rpm_limit >= 1000 && rpm_limit <= 7500;
    }
};

enum class Fault : std::uint32_t {
    none = 0, interlock = 1, power = 2, sensor = 4, stale = 8,
    sync = 16, overspeed = 32, hot = 64, uncalibrated = 128,
    lambda = 256, timing = 512,
};

inline Fault operator|(Fault a, Fault b) {
    return static_cast<Fault>(static_cast<std::uint32_t>(a)|static_cast<std::uint32_t>(b));
}

inline bool plausible(const Sensors& s) {
    const std::array<double, 8> v{s.map_kpa,s.tps_percent,s.clt_c,s.iat_c,s.lambda,s.battery_v,s.sensor_v,0};
    for (auto x : v) if (!std::isfinite(x)) return false;
    return s.valid && s.map_kpa >= 10 && s.map_kpa <= 110 && s.tps_percent >= 0 && s.tps_percent <= 100 &&
           s.clt_c >= -40 && s.clt_c <= 140 && s.iat_c >= -40 && s.iat_c <= 110 &&
           s.battery_v >= 7 && s.battery_v <= 18 && s.sensor_v >= 4.75 && s.sensor_v <= 5.25 &&
           (!s.lambda_ready || (s.lambda >= .65 && s.lambda <= 1.5));
}

inline Fault inhibit(const Calibration& c, const Sensors& s, double rpm, bool sync,
                     bool interlock, bool power_good, bool timing_ok, std::uint64_t now) {
    Fault f = Fault::none;
    if (!c.valid() || !c.vehicle_reviewed) f = f|Fault::uncalibrated;
    if (!interlock) f = f|Fault::interlock;
    if (!power_good) f = f|Fault::power;
    if (!timing_ok) f = f|Fault::timing;
    if (!plausible(s)) f = f|Fault::sensor;
    if (now < s.sampled_us || now-s.sampled_us > 20000) f = f|Fault::stale;
    if (!sync || !std::isfinite(rpm) || rpm <= 0) f = f|Fault::sync;
    if (!std::isfinite(rpm) || rpm >= c.rpm_limit) f = f|Fault::overspeed;
    if (s.clt_c >= 115) f = f|Fault::hot;
    if (s.clt_c >= 70 && (!s.lambda_ready || s.lambda < .8 || s.lambda > 1.2)) f = f|Fault::lambda;
    return f;
}

// Lambda trim is bounded and rate-limited. A rear narrowband sensor is not
// used to control mixture or represented as a catalyst health measurement.
class LambdaTrim {
public:
    double update(const Sensors& s, double rpm, double dt_s) {
        if (!plausible(s) || !s.lambda_ready || s.clt_c < 70 || s.tps_percent > 60 || rpm < 600 ||
            !std::isfinite(rpm) || !std::isfinite(dt_s) || dt_s <= 0 || dt_s > .1) {
            trim_ = 1;
            return trim_;
        }
        trim_ = std::clamp(trim_+std::clamp((s.lambda-1)*.15*dt_s,-.02*dt_s,.02*dt_s),.9,1.1);
        return trim_;
    }
private:
    double trim_ = 1;
};

struct Demand { double pulse_ms = 0, dwell_ms = 0, advance_deg = 0; bool valid = false; };

inline Demand demand(const Calibration& c, const Sensors& s, double rpm, double ve, double advance_deg, double trim) {
    if (!c.valid() || !plausible(s) || !std::isfinite(rpm) || rpm <= 0 || rpm >= c.rpm_limit ||
        !std::isfinite(ve) || ve < .2 || ve > 1.2 || !std::isfinite(advance_deg) ||
        advance_deg < -5 || advance_deg > 40 || !std::isfinite(trim) || trim < .9 || trim > 1.1) return {};
    const double volume_m3 = c.displacement_cc/c.cylinders*1e-6;
    const double air_mg = s.map_kpa*1000*volume_m3*ve/(287.05*(s.iat_c+273.15))*1e6;
    const double fuel_mg = air_mg/c.stoich_afr*trim;
    const double flow_mg_ms = c.injector_cc_min*c.fuel_density_g_cc/60;
    // Batch injection once per 360 degrees: half the 720-degree fuel mass,
    // with dead time applied to each physical opening.
    const double pw = fuel_mg/(2*flow_mg_ms)+c.injector_deadtime_ms;
    const double revolution_ms = 60000/rpm;
    // Reject insufficient injector capacity instead of silently clipping fuel.
    if (!std::isfinite(pw) || pw <= 0 || pw > 15 || pw > revolution_ms*c.max_duty) return {};
    return {pw, c.max_dwell_ms, advance_deg, true};
}

struct Edge { std::uint64_t time_us; unsigned channel; bool high; };

// A bounded monotonic edge queue, independent of hardware drivers. Target
// integration must use a hardware compare ISR, never vTaskDelay for spark.
class PulseQueue {
public:
    static constexpr std::size_t capacity = 32;
    bool insert_pulse(unsigned channel, std::uint64_t start, std::uint64_t width,
                      std::uint64_t now) {
        if (channel >= 8 || width == 0 || width > (channel < 4 ? 15000U : 3500U) ||
            start <= now || start > std::numeric_limits<std::uint64_t>::max()-width ||
            size_+2 > capacity) return false;
        const auto finish = start+width;
        // Do not allow overlapping pulses on a channel, including an active
        // pulse whose leading edge has already been consumed.
        if (active_ & (1U << channel)) return false;
        for (std::size_t i=0; i<size_; ++i) {
            if (edges_[i].channel == channel) return false;
        }
        edges_[size_++] = {start, channel, true};
        edges_[size_++] = {finish, channel, false};
        std::sort(edges_.begin(),edges_.begin()+size_,[](const auto& a,const auto& b) {
            return a.time_us < b.time_us || (a.time_us == b.time_us && a.high < b.high);
        });
        return true;
    }
    template <typename Write> bool dispatch(std::uint64_t now, Write write) {
        if (seen_time_ && now < last_now_) { cut(write); return false; }
        seen_time_ = true; last_now_ = now;
        while (size_ && edges_[0].time_us <= now) {
            const auto e = edges_[0];
            if (now-e.time_us > 25) { cut(write); return false; }
            write(e.channel,e.high);
            if (e.high) active_ |= 1U << e.channel;
            else active_ &= ~(1U << e.channel);
            std::move(edges_.begin()+1,edges_.begin()+size_,edges_.begin());
            --size_;
        }
        return true;
    }
    template <typename Write> void cut(Write write) {
        size_ = 0; active_ = 0;
        for (unsigned ch=0; ch<8; ++ch) write(ch,false);
    }
    std::size_t size() const { return size_; }
private:
    std::array<Edge,capacity> edges_{};
    std::size_t size_ = 0;
    unsigned active_ = 0;
    std::uint64_t last_now_ = 0;
    bool seen_time_ = false;
};

} // namespace ecu
