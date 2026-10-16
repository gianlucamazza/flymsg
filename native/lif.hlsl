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
cbuffer Tick : register(b0) {
    uint tick; uint phase; uint words;
    // version 2 (all zero for version 1): extension offsets into input and state,
    // counts, and where the graded-source synapse lists start in `outs`
    uint ng; uint nc; uint ncomp; uint width; uint gbase;
    uint x_gcol; uint x_lo; uint x_span; uint x_scale; uint x_gpos; uint x_nodes;
    uint x_off; uint x_moff; uint x_mat; uint x_amp;
    uint s_ring; uint s_new; uint s_vsum; uint s_buf; uint s_pulse;
}
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
// raw words of the extension: input at an absolute word, state likewise
uint xin(uint at) { return input.Load(at*4); }
double xd(uint at) { uint2 r=input.Load2(at*4); return asdouble(r.x,r.y); }
uint sw(uint at) { return state.Load(at*4); }
void sput(uint at,uint v) { state.Store(at*4,v); }
// a / b rounded to nearest even as float32, for 0 < a < b, b in [2^-126, 2^126]
// (the host checks it, so 1/b is a normal float32): Newton in
// double from a float32 reciprocal, then the exact test against the midpoints
// beside the candidate (a midpoint has 25 bits and b 24, so midpoint * b is
// exact in double, as is every comparison)
uint fdiv_unit(uint a,uint b) {
    precise double A=f64(a),B=f64(b);
    precise double r=(double)(1.0f/asfloat(b));
    r=r*(2.0-B*r); r=r*(2.0-B*r);
    precise double est=A*r;
    uint q=f32(est);
    for(uint k=0;k<8;++k) {
        precise double hi=(f64(q)+f64(q+1u))*0.5;
        precise double ph=hi*B;
        if(A>ph || (A==ph && (q&1u)!=0)) { q=q+1u; continue; }
        if(q>0u) {
            precise double lo=(f64(q-1u)+f64(q))*0.5;
            precise double pl=lo*B;
            if(A<pl || (A==pl && (q&1u)!=0)) { q=q-1u; continue; }
        }
        break;
    }
    return q;
}
[numthreads(64,1,1)]
void CSMain(uint3 thread : SV_DispatchThreadID) {
    uint i=thread.x,n=h(2);
    if(phase==4) {
        // one coupled row: its group's exact step in float64 from the state
        // before the update (potentials relative to rest, conductances of
        // non-refractory members, active spike terms), as the CPU sums it
        if(i>=nc) return;
        uint c=0,top=ncomp; // the group whose rows hold i: off[c] <= i < off[c+1]
        while(top-c>1) { uint mid=(c+top)/2; if(xin(x_off+mid)<=i) c=mid; else top=mid; }
        uint a=xin(x_off+c),m=xin(x_off+c+1)-a,row=xin(x_moff+c)+(i-a)*3*m;
        precise double rest=f64(h(13)),acc=0.0;
        for(uint q=0;q<m;++q) {
            precise double t=xd(x_mat+2*(row+q))*(f64(word(25,xin(x_nodes+a+q)))-rest);
            acc=acc+t;
        }
        for(uint q2=0;q2<m;++q2) {
            uint j=xin(x_nodes+a+q2);
            if(word(28,j)<=tick) {
                precise double t=xd(x_mat+2*(row+m+q2))*f64(word(26,j));
                acc=acc+t;
            }
        }
        for(uint q3=0;q3<m;++q3)
            if(asint(sw(s_pulse+a+q3))>0) {
                precise double t=xd(x_mat+2*(row+2*m+q3))*xd(x_amp+2*(a+q3));
                acc=acc+t;
            }
        precise double v=rest+acc;
        sput(s_buf+i,f32(v));
        return;
    }
    if(i>=n) return;
    int gpos=nc!=0?asint(xin(x_gpos+i)):-1;
    int gk=ng!=0?asint(xin(x_gcol+i)):-1;
    if(phase==0) {
        if(gpos>=0 && asint(sw(s_pulse+(uint)gpos))>0)
            sput(s_pulse+(uint)gpos,sw(s_pulse+(uint)gpos)-1u);
        bool frozen=word(28,i)>tick;
        uint g=word(26,i);
        uint vi=fadd(fadd(fmul(fsub(word(25,i),h(13)),h(9)),fmul(g,h(11))),h(13));
        if(gpos>=0 && !frozen) vi=sw(s_buf+(uint)gpos);
        put(25,i,frozen?h(13):vi);if(!frozen)put(26,i,fmul(g,h(10)));
        put(27,i,fmul(word(27,i),h(12)));
    } else if(phase==1) {
        uint threshold=fadd(h(14),word(27,i));
        put(33,i,f64(word(25,i))>f64(threshold) && inp(20,i)==0 && gk<0 ? 1:0);
        if(gk>=0) {
            // release = clamp((v - lo) / span, 0, 1) * scale; 0 when silenced
            uint f=0u,a=fsub(word(25,i),xin(x_lo+(uint)gk)),b=xin(x_span+(uint)gk);
            if((a&0x80000000u)==0 && a!=0u)
                f=f64(a)>=f64(b)?asuint(1.0f):fdiv_unit(a,b);
            sput(s_new+(uint)gk,inp(20,i)!=0?0u:fmul(f,xin(x_scale+(uint)gk)));
        }
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
        if(ng!=0) {
            // graded release from d steps ago, sources ascending
            uint released=0u; bool touched=false;
            uint gslot=(tick%h(5))*ng;
            for(uint k=outs.Load((gbase+i)*4);k<outs.Load((gbase+i+1)*4);++k) {
                uint q=outs.Load(k*4);
                uint r=sw(s_ring+gslot+xin(x_gcol+inp(17,q)));
                if((r&0x7fffffffu)==0u) continue;
                released=fadd(released,fmul(inp(18,q),r));
                touched=true;
            }
            if(touched && word(28,i)<=tick) put(26,i,fadd(word(26,i),released));
        }
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
            if(width!=0 && gpos>=0) sput(s_pulse+(uint)gpos,width);
            uint base=(tick%h(5))*words,prior;
            for(uint k=outs.Load(i*4);k<outs.Load((i+1)*4);++k) {
                uint q=outs.Load(k*4);
                active.InterlockedOr((base+(q>>5))*4,1u<<(q&31),prior);
            }
        }
        put(29,(tick%h(5))*n+i,emitted);
        if(gk>=0) {
            // this step's release into the ring; the bin's potential sum, float64
            sput(s_ring+(tick%h(5))*ng+(uint)gk,sw(s_new+(uint)gk));
            uint at=s_vsum+2*((tick/h(4))*ng+(uint)gk);
            precise double sum=asdouble(sw(at),sw(at+1))+f64(word(25,i));
            uint lo,hi;asuint(sum,lo,hi);sput(at,lo);sput(at+1,hi);
        }
    }
}
