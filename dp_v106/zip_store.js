// zip_store.js — 외부 라이브러리 없는 순수 JS ZIP 작성기 (무압축 store 방식, CSP 안전)
// v21.8.24.92: 묶음 내보내기가 파일 8~10개를 연속 다운로드(브라우저 차단/순서 섞임/저장 꼬임 위험)하던 것을
// ZIP 1개 파일로 묶기 위한 모듈. JPG/GIF는 이미 압축돼 있어 store(무압축)로 충분하다.
(function(){
  'use strict';

  // 표준 CRC-32 (poly 0xEDB88320)
  const CRC_TABLE = (function(){
    const t = new Uint32Array(256);
    for(let n = 0; n < 256; n++){
      let c = n;
      for(let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();
  function crc32(bytes){
    let c = 0xFFFFFFFF;
    for(let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function dosDateTime(d){
    d = d || new Date();
    const time = ((d.getHours() & 31) << 11) | ((d.getMinutes() & 63) << 5) | ((d.getSeconds() / 2) & 31);
    const date = (((d.getFullYear() - 1980) & 127) << 9) | (((d.getMonth() + 1) & 15) << 5) | (d.getDate() & 31);
    return { time, date };
  }

  // files: [{name:string, bytes:Uint8Array}] → Uint8Array(zip)
  function make(files, when){
    const enc = new TextEncoder();
    const { time, date } = dosDateTime(when);
    const parts = []; let offset = 0;
    const central = []; let cdSize = 0;
    const push = (u8) => { parts.push(u8); offset += u8.length; };
    const u16 = (v) => new Uint8Array([v & 255, (v >> 8) & 255]);
    const u32 = (v) => new Uint8Array([v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255]);

    for(const f of files){
      const name = enc.encode(String(f.name || 'file'));
      const data = f.bytes instanceof Uint8Array ? f.bytes : new Uint8Array(f.bytes || []);
      const crc = crc32(data);
      const headOffset = offset;
      // Local File Header (flags bit11 = UTF-8 파일명)
      push(new Uint8Array([0x50,0x4B,0x03,0x04]));
      push(u16(20)); push(u16(0x0800)); push(u16(0)); // ver, flags(UTF-8), method=store
      push(u16(time)); push(u16(date));
      push(u32(crc)); push(u32(data.length)); push(u32(data.length));
      push(u16(name.length)); push(u16(0));
      push(name); push(data);
      // Central Directory entry
      const cd = [];
      cd.push(new Uint8Array([0x50,0x4B,0x01,0x02]));
      cd.push(u16(20)); cd.push(u16(20)); cd.push(u16(0x0800)); cd.push(u16(0));
      cd.push(u16(time)); cd.push(u16(date));
      cd.push(u32(crc)); cd.push(u32(data.length)); cd.push(u32(data.length));
      cd.push(u16(name.length)); cd.push(u16(0)); cd.push(u16(0));
      cd.push(u16(0)); cd.push(u16(0)); cd.push(u32(0));
      cd.push(u32(headOffset));
      cd.push(name);
      const cdEntry = concat(cd);
      central.push(cdEntry); cdSize += cdEntry.length;
    }
    const cdStart = offset;
    central.forEach(push);
    // End of Central Directory
    push(new Uint8Array([0x50,0x4B,0x05,0x06]));
    push(u16(0)); push(u16(0));
    push(u16(files.length)); push(u16(files.length));
    push(u32(cdSize)); push(u32(cdStart));
    push(u16(0));
    return concat(parts);
  }

  function concat(arr){
    let len = 0; arr.forEach(a => len += a.length);
    const out = new Uint8Array(len); let o = 0;
    arr.forEach(a => { out.set(a, o); o += a.length; });
    return out;
  }

  const api = { make, _crc32: crc32 };
  if(typeof window !== 'undefined') window.DP_ZIP = api;
  if(typeof module !== 'undefined' && module.exports) module.exports = api;
})();
