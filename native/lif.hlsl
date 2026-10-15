// ordered-f32-double-kicks: requires hardware double precision shader ops, and
// shader model 6.2 built with -denorm preserve so float32 subnormals match the
// CPU oracle (a decaying conductance reaches them on long runs).
ByteAddressBuffer input : register(t0);
RWByteAddressBuffer state : register(u0);
// outgoing synapses (n + 1 offsets, then incoming-CSR positions) and the delivery
// bitset (one slot of `words` per delay-ring slot, a bit per incoming synapse)
ByteAddressBuffer outs : register(t1);
RWByteAddressBuffer active : register(u1);
cbuffer Tick : register(b0) { uint tick; uint phase; uint words; }
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
        // the set bits of this neuron's synapses, ascending q: the pull loop's sum
        precise float delivered=0;
        uint q0=inp(16,i),q1=inp(16,i+1),base=(tick%h(5))*words;
        for(uint w=q0>>5;q0<q1 && w<=((q1-1)>>5);++w) {
            uint lo=w==(q0>>5)?(q0&31):0,hi=w==((q1-1)>>5)?((q1-1)&31):31;
            uint mask=(hi==31?0xffffffffu:((1u<<(hi+1))-1u))&~((1u<<lo)-1u);
            uint bits=active.Load((base+w)*4)&mask;
            if(bits!=0) {
                for(uint m=bits;m!=0;m&=m-1)
                    delivered=delivered+asfloat(inp(18,(w<<5)+firstbitlow(m)));
                uint prior;active.InterlockedAnd((base+w)*4,~bits,prior);
            }
        }
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
            uint base=(tick%h(5))*words,prior;
            for(uint k=outs.Load(i*4);k<outs.Load((i+1)*4);++k) {
                uint q=outs.Load(k*4);
                active.InterlockedOr((base+(q>>5))*4,1u<<(q&31),prior);
            }
        }
        put(29,(tick%h(5))*n+i,emitted);
    }
}
