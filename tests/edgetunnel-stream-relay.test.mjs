import {test} from 'node:test';
import assert from 'node:assert/strict';
import {connectStreams} from '../cloudflare/edgetunnel/stream-relay.mjs';
globalThis.WebSocket={OPEN:1};
globalThis.log=()=>{};
globalThis.closeSocketQuietly=ws=>{ws.closed=true};
function socket(chunks, fail=false) {
  let i=0;
  return {closed:Promise.resolve(),close(){this.wasClosed=true},
    readable:new ReadableStream({pull(c){if(i<chunks.length)c.enqueue(Uint8Array.from(chunks[i++]));else if(fail)c.error(new Error('upstream lost'));else c.close();}})};
}
function ws() {return {readyState:1,bytes:[],send(b){this.bytes.push(...b)}}}
test('fragmented binary data retains every byte and adds a header once',async()=>{
 const a=socket([[0,255],[],[1],[2,3]]),b=ws();let headers=0;
 await connectStreams(a,b,()=>{headers++;return Uint8Array.of(7,8)},null);
 assert.deepEqual(b.bytes,[7,8,0,255,1,2,3]);assert.equal(headers,1);assert.ok(a.wasClosed&&b.closed);
});
test('large data is forwarded byte-exact without truncation',async()=>{
 const bytes=Array.from({length:250000},(_,i)=>i%251),a=socket([bytes.slice(0,60000),bytes.slice(60000)]),b=ws();
 b.send=function(chunk){for(const x of chunk)this.bytes.push(x)};
 await connectStreams(a,b,null,null);assert.deepEqual(b.bytes,bytes);
});
test('empty failed connection retries once, without closing replacement WebSocket',async()=>{
 const a=socket([],true),b=ws();let retries=0;
 await connectStreams(a,b,null,async()=>{retries++});assert.equal(retries,1);assert.ok(!b.closed);
});
test('partial data followed by failure is never retried or replayed',async()=>{
 const a=socket([[1,2]],true),b=ws();let retries=0;
 await connectStreams(a,b,null,()=>{retries++});assert.equal(retries,0);assert.deepEqual(b.bytes,[1,2]);assert.ok(b.closed);
});
test('async adapters are awaited and preserve order',async()=>{
 const a=socket([[1],[2],[3]]),b=ws();let busy=false;
 b.send=async function(chunk){assert.equal(busy,false);busy=true;await new Promise(r=>setImmediate(r));this.bytes.push(...chunk);busy=false};
 await connectStreams(a,b,null,null);assert.deepEqual(b.bytes,[1,2,3]);
});
test('retired connection cannot send or close the successor WebSocket',async()=>{
 const a=socket([[1],[2]]),b=ws();let active=true;
 b.send=function(chunk){this.bytes.push(...chunk);active=false};
 await connectStreams(a,b,null,null,()=>active);assert.deepEqual(b.bytes,[1]);assert.ok(!b.closed);
});
test('stop waits for the current async send and suppresses later chunks',async()=>{
 const a=socket([[1],[2]]),b=ws(),wrapper={};let release;const gate=new Promise(r=>release=r);
 b.send=async function(chunk){await gate;this.bytes.push(...chunk)};
 const task=connectStreams(a,b,null,null,null,wrapper);await new Promise(r=>setImmediate(r));
 let stopped=false;const stopping=wrapper.downlinkController.停止并刷新().then(()=>stopped=true);
 await new Promise(r=>setImmediate(r));assert.equal(stopped,false);release();await Promise.all([task,stopping]);
 assert.deepEqual(b.bytes,[1]);assert.ok(!b.closed);assert.equal(wrapper.downlinkController,null);
});
