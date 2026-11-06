// Time-resolved synthetic circuit replay through the real Capture/Controller.
// No ESP32, GPIO, scheduler, engine plant or physical protection is executed.
#include "ecu/engine_log_msl.hpp"
#include "ecu/engine_binding.hpp"
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace {
constexpr unsigned phases = 10;
ecu::engine::Tune make_tune(unsigned strategy) {
    ecu::engine::Tune t;
    t.strategy = static_cast<ecu::engine::Strategy>(strategy);
    t.afterstart_pct = 0;
    t.dfco_enabled = false;
    t.warmup_pct.fill(100);
    t.crank_pct.fill(100);
    t.spark.cells.fill(20);
    t.transient_enrichment.mode = ecu::transient::Mode::Off;
    t.flex_fuel.correction.enabled = true;
    t.flex_fuel.correction.temperature_enabled = true;
    for (unsigned n = 0; n < 6; ++n) {
        t.flex_fuel.correction.fuel_pct[n] = 100 + 10 * n;
        t.flex_fuel.correction.spark_deg[n] = 2 * n;
        t.flex_fuel.correction.temperature_pct[n] =
            100 + (t.flex_fuel.correction.temperature_c[n] - 20) * .1f;
    }
    return t;
}

ecu::config::Config make_profile(bool ratiometric) {
    ecu::config::Config c;
    const char* ids[] = {"map", "tps", "clt", "iat", "wideband", "postcat"};
    const char* units[] = {"kPa", "%", "C", "C", "lambda", "V"};
    for (unsigned n = 0; n < 6; ++n) {
        auto& s = c.sensors[n];
        std::snprintf(s.id, sizeof(s.id), "%s", ids[n]);
        std::snprintf(s.label, sizeof(s.label), "Synthetic %s fixture", ids[n]);
        std::snprintf(s.unit, sizeof(s.unit), "%s", units[n]);
        s.confirmed = true;
        s.mode = n == 5 ? ecu::config::Mode::Voltage : ecu::config::Mode::Linear;
        s.points[0] = {.5, 0}; s.points[1] = {4.5, 100};
    }
    c.sensors[0].y0 = 10; c.sensors[0].y1 = 110;
    c.sensors[0].ratiometric = c.sensors[1].ratiometric = ratiometric;
    // Optional physical R32/R33 are assumed fitted only in this fixture.
    for (unsigned n : {2U, 3U}) {
        c.sensors[n].mode = ecu::config::Mode::Ntc;
        c.sensors[n].pullup_fitted = true;
    }
    c.sensors[4].y0 = .5; c.sensors[4].y1 = 1.5;
    return c;
}

std::uint64_t quantize(double time, unsigned phase) {
    return static_cast<std::uint64_t>(std::floor(time + phase / 10.));
}
}

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    try {
        std::size_t used = 0;
        const unsigned long strategy = std::stoul(argv[1], &used);
        if (used != std::string(argv[1]).size() || strategy > 2) return 2;
        const auto tune = make_tune(static_cast<unsigned>(strategy));
        if (ecu::engine::validate(tune)) return 2;
        const std::string basis(argv[2]);
        if (basis != "absolute" && basis != "ratiometric") return 2;
        const auto profile = make_profile(basis == "ratiometric");
        if (!ecu::config::valid(profile)) return 2;
        const std::filesystem::path output(argv[3]);
        if (!std::filesystem::create_directory(output)) return 2;
        std::array<ecu::flex::Capture, phases> captures;
        std::array<ecu::engine::Controller, phases> controllers;
        std::vector<ecu::engine_log::Row> rows;
        double previous = -1;
        unsigned events = 0, queries = 0;
        std::string line;
        while (std::getline(std::cin, line)) {
            std::istringstream input(line);
            char kind;
            double time;
            if (!(input >> kind >> time) || !std::isfinite(time) || time < 0 ||
                time < previous || time > 1e12 || ++events > 100000) return 2;
            previous = time;
            if (kind == 'E') {
                unsigned level;
                if (!(input >> level) || level > 1) return 2;
                for (unsigned phase = 0; phase < phases; ++phase)
                    captures[phase].edge(quantize(time, phase), level != 0,
                                         ecu::flex::Source::Synthetic);
            } else if (kind == 'Q') {
                double sampled, adc_ref;
                unsigned adc_ok;
                ecu::web::Sample sample;
                if (!(input >> sampled >> adc_ok >> adc_ref) ||
                    !std::isfinite(sampled) || sampled < 0 || sampled > time ||
                    adc_ok > 1 || !std::isfinite(adc_ref) || adc_ref <= 0 ||
                    ++queries > 10000) return 2;
                for (auto& value : sample.raw)
                    if (!(input >> value) || value > 4095) return 2;
                sample.adc_ok = adc_ok != 0;
                sample.rpm = 2000;
                sample.synced = sample.phase_synced = true;
                for (unsigned phase = 0; phase < phases; ++phase) {
                    const auto now = quantize(time, phase);
                    const auto observation = captures[phase].observe(now);
                    const auto bound = ecu::engine::bind_inputs(sample, profile,
                        quantize(sampled, phase), &tune);
                    auto in = bound.input;
                    in.flex_sample = {observation, tune.flex_fuel.capture, tune.revision};
                    const auto control = controllers[phase].step(tune, in, now);
                    // The actual completed invalid controller evaluation comes
                    // before ACK, exactly as required by the portable contract.
                    bool acknowledged = false;
                    if (observation.pending_fault && !control.flex_fuel.control_ok &&
                        control.fuel_cut && control.spark_cut)
                        acknowledged = captures[phase].acknowledge(observation.fault_generation);
                    auto data = ecu::engine::synthetic_data(tune, in, control, queries, now);
                    // Raw counts are model/fixture observations, never hardware.
                    data.board_flags = sample.adc_ok ? 1 : 0;
                    data.sensor_revision = profile.revision;
                    data.input_valid = ecu::engine::data_input_mask(in, bound.qualified);
                    for (unsigned n = 0; n < 8; ++n) data.raw_adc[n] = sample.raw[n];
                    const double map_adc = sample.raw[0] * profile.adc_reference_v / 4095;
                    const double map_basis = ecu::config::transfer_voltage(profile.sensors[0],
                        map_adc / .6, in.sensor_v);
                    auto* json = ecu::engine::data_json(data, now);
                    if (!json) return 3;
                    const bool fields = cJSON_AddNumberToObject(json, "circuit_clock_phase_us", phase / 10.) &&
                        cJSON_AddNumberToObject(json, "circuit_adc7_code", sample.raw[7]) &&
                        cJSON_AddNumberToObject(json, "circuit_adc_reference_v", adc_ref) &&
                        cJSON_AddBoolToObject(json, "circuit_fault_acknowledged", acknowledged) &&
                        cJSON_AddBoolToObject(json, "physical_execution", false) &&
                        cJSON_AddBoolToObject(json, "circuit_ratiometric", basis == "ratiometric") &&
                        cJSON_AddNumberToObject(json, "circuit_map_transfer_v", map_basis) &&
                        cJSON_AddNumberToObject(json, "circuit_map_error_kpa", in.map_qualified ? in.map_kpa - 50 : NAN) &&
                        cJSON_AddNumberToObject(json, "circuit_tps_error_pct", in.tps_pct - 10);
                    char* text = fields ? cJSON_PrintUnformatted(json) : nullptr;
                    cJSON_Delete(json);
                    if (!text) return 3;
                    std::cout << text << '\n';
                    cJSON_free(text);
                    if (phase == 0) rows.push_back({data, now, 1, queries});
                }
            } else return 2;
            std::string extra;
            if (input >> extra) return 2;
        }
        if (!std::cin.eof() || rows.empty()) return 2;
        ecu::engine_log::Header header;
        header.state = ecu::engine_log::State::Stopped;
        header.source = ecu::engine::DataSource::Synthetic;
        header.log_id = 1;
        header.period_ms = 5;
        header.duration_s = static_cast<unsigned>(rows.back().recorded_us / 1000000 + 1);
        header.total = header.retained = static_cast<std::uint32_t>(rows.size());
        header.started_us = rows.front().recorded_us;
        header.ended_us = rows.back().recorded_us;
        std::array<char, ecu::engine_log::text_capacity> text;
        std::ofstream msl(output / "engine.msl");
        if (!msl || !ecu::engine_log::msl_header(header, text.data(), text.size(),
                                               "synthetic-circuit-no-target")) return 3;
        msl << text.data();
        for (const auto& row : rows) {
            if (!ecu::engine_log::msl_row(header, row, text.data(), text.size())) return 3;
            msl << text.data();
        }
        return msl && std::cout ? 0 : 3;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
