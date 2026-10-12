// ordered-f32-double-kicks: requires hardware double precision shader ops.
ByteAddressBuffer input : register(t0);
RWByteAddressBuffer state : register(u0);
cbuffer Tick : register(b0) { uint tick; uint phase; }
uint h(uint slot) { return input.Load(slot * 4); }
uint inp(uint slot, uint i) { return input.Load((h(slot) + i) * 4); }
uint word(uint slot, uint i) { return state.Load((h(slot) + i) * 4); }
float val(uint slot, uint i) { return asfloat(word(slot,i)); }
float c(uint at) { return asfloat(h(at)); }
void put(uint slot,uint i,uint v) { state.Store((h(slot)+i)*4,v); }
void putf(uint slot,uint i,float v) { put(slot,i,asuint(v)); }
[numthreads(64,1,1)]
void CSMain(uint3 thread : SV_DispatchThreadID) {
    uint i=thread.x,n=h(2); if(i>=n) return;
    if(phase==0) {
        bool frozen=word(28,i)>tick;
        precise float shifted=val(25,i)-c(13);
        precise float leak=shifted*c(9);
        precise float syn=val(26,i)*c(11);
        precise float total=leak+syn;
        precise float vi=total+c(13);
        precise float gi=val(26,i)*c(10);
        putf(25,i,frozen?c(13):vi);if(!frozen)putf(26,i,gi);
        precise float th=val(27,i)*c(12);putf(27,i,th);
    } else if(phase==1) {
        precise float threshold=c(14)+val(27,i);
        put(33,i,val(25,i)>threshold && inp(20,i)==0 ? 1:0);
    } else if(phase==2) {
        precise float delivered=0;
        for(uint q=inp(16,i);q<inp(16,i+1);++q)
            if(word(29,(tick%h(5))*n+inp(17,q))!=0) delivered=delivered+asfloat(inp(18,q));
        if(word(28,i)<=tick) {precise float g=val(26,i)+delivered;putf(26,i,g);}
        int col=asint(inp(23,i));
        if(col>=0) {
            uint at=h(24)+(tick*h(7)+(uint)col)*2;
            uint2 raw=input.Load2(at*4);
            precise double count=asdouble(raw.x,raw.y);
            precise double kick=(double)c(15)*count;
            precise double v=(double)val(25,i)+kick;
            putf(25,i,(float)v);
        }
    } else if(phase==3) {
        uint emitted=word(33,i);
        if(emitted!=0) {
            putf(25,i,c(13));putf(26,i,0);
            precise float th=val(27,i)+asfloat(inp(21,i));putf(27,i,th);
            if(inp(19,i)==0)put(28,i,tick+h(6));
            uint at=(tick/h(4))*n+i;put(30,at,word(30,at)+1);
            if(asint(word(31,i))<0)put(31,i,tick);
            int col=asint(inp(22,i));if(col>=0)put(32,tick*h(8)+(uint)col,1);
        }
        put(29,(tick%h(5))*n+i,emitted);
    }
}
