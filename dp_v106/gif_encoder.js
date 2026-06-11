// gif_encoder.js — 외부 라이브러리/워커 없이 순수 JS GIF89a 인코더 (CSP 안전)
// v21.8.24.70: 상세페이지 상단/중간/하단에 넣을 '정지컷 모션 GIF'(줌·팬·샤인) 출력용.
// 프레임은 호출측(content.js)이 캔버스로 렌더해 RGBA로 넘겨주고, 여기서 256색 양자화 + LZW로 GIF 바이트를 만든다.
(function(){
  'use strict';

  // ---- median-cut 256색 팔레트 (모든 프레임 공유 → 용량/일관성 유리) ----
  function makeBox(pixels){
    let rmin=255,rmax=0,gmin=255,gmax=0,bmin=255,bmax=0,rs=0,gs=0,bs=0;
    for(let i=0;i<pixels.length;i++){
      const p=pixels[i];
      const r=p[0],g=p[1],b=p[2];
      if(r<rmin)rmin=r; if(r>rmax)rmax=r;
      if(g<gmin)gmin=g; if(g>gmax)gmax=g;
      if(b<bmin)bmin=b; if(b>bmax)bmax=b;
      rs+=r; gs+=g; bs+=b;
    }
    const n=pixels.length||1;
    const rr=rmax-rmin, gr=gmax-gmin, br=bmax-bmin;
    return { pixels, count:pixels.length, range:Math.max(rr,gr,br),
      ch:(rr>=gr&&rr>=br)?0:(gr>=br?1:2),
      avg:[Math.round(rs/n),Math.round(gs/n),Math.round(bs/n)] };
  }
  function splitBox(box){
    const ch=box.ch;
    const sorted=box.pixels.slice().sort((a,b)=>a[ch]-b[ch]);
    const mid=sorted.length>>1;
    return [makeBox(sorted.slice(0,mid)), makeBox(sorted.slice(mid))];
  }
  function buildPalette(frames, maxColors){
    maxColors=maxColors||256;
    const samples=[];
    const totalPx=frames[0].width*frames[0].height;
    const stride=Math.max(1, Math.floor(totalPx/8000)); // 프레임당 ~8k 픽셀 샘플
    for(let fi=0; fi<frames.length; fi++){
      const d=frames[fi].data;
      for(let i=0, px=0; i<d.length; i+=4, px++){
        if(px % stride) continue;
        samples.push([d[i],d[i+1],d[i+2]]);
      }
    }
    if(!samples.length) samples.push([0,0,0]);
    let boxes=[makeBox(samples)];
    while(boxes.length<maxColors){
      let idx=-1, best=-1;
      for(let i=0;i<boxes.length;i++){ if(boxes[i].count>1 && boxes[i].range>best){ best=boxes[i].range; idx=i; } }
      if(idx<0) break;
      const sp=splitBox(boxes[idx]);
      boxes.splice(idx,1,sp[0],sp[1]);
    }
    const palette=new Uint8Array(256*3);
    for(let i=0;i<boxes.length;i++){ const c=boxes[i].avg; palette[i*3]=c[0]; palette[i*3+1]=c[1]; palette[i*3+2]=c[2]; }
    return { palette, count:boxes.length };
  }

  // ---- 5비트 색큐브 룩업(32768) → 인덱스. 픽셀별 최근접 탐색을 한 번만 미리 계산 ----
  function buildLookup(palette, count){
    const lut=new Uint8Array(32768);
    for(let key=0;key<32768;key++){
      const r=((key>>10)&31)<<3, g=((key>>5)&31)<<3, b=(key&31)<<3;
      let bi=0,bd=1e9;
      for(let i=0;i<count;i++){
        const dr=r-palette[i*3], dg=g-palette[i*3+1], db=b-palette[i*3+2];
        const d=dr*dr+dg*dg+db*db;
        if(d<bd){ bd=d; bi=i; }
      }
      lut[key]=bi;
    }
    return lut;
  }
  function mapFrame(data, lut){
    const n=data.length>>2;
    const out=new Uint8Array(n);
    for(let i=0,j=0;i<n;i++,j+=4){
      out[i]=lut[((data[j]>>3)<<10)|((data[j+1]>>3)<<5)|(data[j+2]>>3)];
    }
    return out;
  }

  // ---- GIF-LZW 압축 ----
  function lzwEncode(indexed, minCodeSize){
    const clear=1<<minCodeSize, eoi=clear+1;
    let codeSize=minCodeSize+1, next=eoi+1;
    let dict=new Map();
    const out=[]; let cur=0, curBits=0;
    const emit=(code)=>{ cur |= code<<curBits; curBits+=codeSize; while(curBits>=8){ out.push(cur&0xff); cur>>=8; curBits-=8; } };
    const clearDict=()=>{ dict=new Map(); next=eoi+1; codeSize=minCodeSize+1; };
    emit(clear); clearDict();
    let prefix=indexed[0];
    for(let i=1;i<indexed.length;i++){
      const k=indexed[i];
      const key=prefix*256+k;
      if(dict.has(key)){ prefix=dict.get(key); }
      else {
        emit(prefix);
        dict.set(key,next++);
        if(next===(1<<codeSize) && codeSize<12) codeSize++;
        if(next===4096){ emit(clear); clearDict(); }
        prefix=k;
      }
    }
    emit(prefix);
    emit(eoi);
    if(curBits>0) out.push(cur&0xff);
    return out;
  }

  // ---- 조립 ----
  function fromFrames(frames, opts){
    opts=opts||{};
    const W=frames[0].width|0, H=frames[0].height|0;
    const delay=Math.max(2, Math.round((opts.delayMs||80)/10)); // centiseconds
    const loop=(opts.loop==null?0:opts.loop)|0; // 0 = 무한반복
    const pal=buildPalette(frames,256);
    const lut=buildLookup(pal.palette, pal.count);

    const bytes=[];
    const str=(s)=>{ for(let i=0;i<s.length;i++) bytes.push(s.charCodeAt(i)&0xff); };
    const u16=(v)=>{ bytes.push(v&0xff, (v>>8)&0xff); };

    str('GIF89a');
    u16(W); u16(H);
    bytes.push(0xF7, 0x00, 0x00); // 글로벌 색표 256, 8bpp
    for(let i=0;i<256;i++) bytes.push(pal.palette[i*3]||0, pal.palette[i*3+1]||0, pal.palette[i*3+2]||0);
    // NETSCAPE2.0 루프
    bytes.push(0x21,0xFF,0x0B); str('NETSCAPE2.0'); bytes.push(0x03,0x01); u16(loop); bytes.push(0x00);

    for(let f=0; f<frames.length; f++){
      bytes.push(0x21,0xF9,0x04,0x00); u16(delay); bytes.push(0x00,0x00); // GCE
      bytes.push(0x2C); u16(0); u16(0); u16(W); u16(H); bytes.push(0x00);  // Image Descriptor
      bytes.push(8); // min code size
      const lzw=lzwEncode(mapFrame(frames[f].data, lut), 8);
      for(let i=0;i<lzw.length;i+=255){
        const end=Math.min(i+255, lzw.length);
        bytes.push(end-i);
        for(let j=i;j<end;j++) bytes.push(lzw[j]);
      }
      bytes.push(0x00); // block terminator
    }
    bytes.push(0x3B); // trailer
    return new Uint8Array(bytes);
  }

  const api={ fromFrames, buildPalette, _lzwEncode:lzwEncode, _mapFrame:mapFrame, _buildLookup:buildLookup };
  if(typeof window!=='undefined') window.DP_GIF=api;
  if(typeof module!=='undefined' && module.exports) module.exports=api;
})();
