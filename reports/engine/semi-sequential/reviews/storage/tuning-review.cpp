#include "/home/mark/persospace/esp32-ecu/tools/tuning_bridge.cpp"

namespace {long review_limit=-1,review_calls=0,review_blocks=0;void*review_allocate(std::size_t n){++review_calls;if(review_limit==0)return nullptr;if(review_limit>0)--review_limit;auto*p=std::malloc(n);if(p)++review_blocks;return p;}void review_release(void*p){if(p){--review_blocks;std::free(p);}}}
extern "C" void review_budget(long n){review_limit=n;review_calls=0;cJSON_Hooks h{review_allocate,review_release};cJSON_InitHooks(&h);}
extern "C" long review_allocations(){return review_calls;}
extern "C" long review_live(){return review_blocks;}
extern "C" long review_parse_allocations(void*opaque){auto&c=*static_cast<Context*>(opaque);review_budget(-1);auto*j=cJSON_ParseWithOpts(c.backend.document.data(),nullptr,true);const auto result=review_calls;cJSON_Delete(j);return result;}
