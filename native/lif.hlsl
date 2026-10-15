// ordered-f32-double-kicks: requires hardware double precision shader ops.
// Every float32 operation on state goes through double and back (f32 below):
// GPUs may flush float32 subnormals, which a decaying conductance reaches on long
// runs, while the CPU oracle keeps them. A float32 +, - or x computed in double
// and rounded once to float32 is the correctly rounded float32 result (53 >=
// 2 * 24 + 2), and subnormals are read and written as bits, so nothing flushes.
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
float c(uint at) { return asfloat(h(at)); }
void put(uint slot,uint i,uint v) { state.Store((h(slot)+i)*4,v); }
void putf(uint slot,uint i,float v) { put(slot,i,asuint(v)); }
// float32 bits -> exact double, subnormals included
double f64(uint b) {
    if((b&0x7f800000u)!=0) return (double)asfloat(b);
    double m=(double)(b&0x7fffffu)*asdouble(0u,0x36a00000u); // x 2^-149
    return (b&0x80000000u)!=0?-m:m;
}
// double -> float32 bits, rounded to nearest even, subnormals built by hand
uint f32(double x) {
    uint lo,hi;asuint(x,lo,hi);
    uint sign=hi&0x80000000u;
    double a=sign!=0?-x:x;
    if(a>=asdouble(0u,0x38100000u)) return asuint((float)x); // >= 2^-126: normal
    double y=a*asdouble(0u,0x49400000u); // x 2^149: the subnormal's mantissa
    uint m=(uint)y;double f=y-(double)m;
    if(f>0.5 || (f==0.5 && (m&1u)!=0)) m=m+1u;
    return sign|m;
}
uint fadd(uint a,uint b) { precise double r=f64(a)+f64(b); return f32(r); }
uint fsub(uint a,uint b) { precise double r=f64(a)-f64(b); return f32(r); }
uint fmul(uint a,uint b) { precise double r=f64(a)*f64(b); return f32(r); }
[numthreads(64,1,1)]
void CSMain(uint3 thread : SV_DispatchThreadID) {
    uint i=thread.x,n=h(2); if(i>=n) return;
    if(phase==0) {
        bool frozen=word(28,i)>tick;
        uint g=word(26,i);
        uint vi=fadd(fadd(fmul(fsub(word(25,i),h(13)),h(9)),fmul(g,h(11))),h(13));
        put(25,i,frozen?h(13):vi);if(!frozen)put(26,i,fmul(g,h(10)));
        put(27,i,fmul(word(27,i),h(12)));
    } else if(phase==1) {
        uint threshold=fadd(h(14),word(27,i));
        put(33,i,f64(word(25,i))>f64(threshold) && inp(20,i)==0 ? 1:0);
    } else if(phase==2) {
        // the set bits of this neuron's synapses, ascending q: the pull loop's sum
        uint delivered=0; // +0.0
        uint q0=inp(16,i),q1=inp(16,i+1),base=(tick%h(5))*words;
        for(uint w=q0>>5;q0<q1 && w<=((q1-1)>>5);++w) {
            uint lo=w==(q0>>5)?(q0&31):0,hi=w==((q1-1)>>5)?((q1-1)&31):31;
            uint mask=(hi==31?0xffffffffu:((1u<<(hi+1))-1u))&~((1u<<lo)-1u);
            uint bits=active.Load((base+w)*4)&mask;
            if(bits!=0) {
                for(uint m=bits;m!=0;m&=m-1)
                    delivered=fadd(delivered,inp(18,(w<<5)+firstbitlow(m)));
                uint prior;active.InterlockedAnd((base+w)*4,~bits,prior);
            }
        }
        if(word(28,i)<=tick) put(26,i,fadd(word(26,i),delivered));
        int col=asint(inp(23,i));
        if(col>=0) {
            uint at=h(24)+(tick*h(7)+(uint)col)*2;
            uint2 raw=input.Load2(at*4);
            precise double count=asdouble(raw.x,raw.y);
            precise double kick=(double)c(15)*count;
            precise double v=f64(word(25,i))+kick;
            put(25,i,f32(v));
        }
    } else if(phase==3) {
        uint emitted=word(33,i);
        if(emitted!=0) {
            putf(25,i,c(13));putf(26,i,0);
            put(27,i,fadd(word(27,i),inp(21,i)));
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
