#pragma once
#include <cstdlib>
#include <memory>
#include <new>

namespace ecu {
// Pinned IDF no-exceptions libstdc++ may abort inside new(nothrow). These
// fixed-size, non-allocating constructors use checked malloc + placement new.
template<class T>struct HeapObjectDelete {
 void operator()(T*p)const{if(p){p->~T();std::free(p);}}
};
template<class T>std::unique_ptr<T,HeapObjectDelete<T>> heap_object(){
 void*allocation=std::malloc(sizeof(T));
 return std::unique_ptr<T,HeapObjectDelete<T>>(allocation?new(allocation)T:nullptr);
}
}
