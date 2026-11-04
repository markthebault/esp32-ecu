from pathlib import Path
r=Path(__file__).resolve().parents[1]
h=(r/"web/index.html").read_text()
(r/"firmware/main/web_assets.hpp").write_text('inline constexpr char index[]=R"ECU_ASSET('+h+')ECU_ASSET";')
(r/"firmware/main/mock.cpp").write_text("OWNED UNDECLARED GENERATION MUTATION")
