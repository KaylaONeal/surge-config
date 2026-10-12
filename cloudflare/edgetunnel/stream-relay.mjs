// Injected into the pinned upstream module. Keep byte order and retry semantics,
// without per-packet Grain queues, 1 ms timers or BYOB buffer copies.
export async function connectStreams(remoteSocket, webSocket, headerData, retryFunc,
  isCurrentSocket = null, remoteConnWrapper = null) {
  const active = () => !isCurrentSocket || isCurrentSocket();
  let headerPending = true, hasData = false, readError = null;
  let stopped = false, pendingSend = null;
  const reader = remoteSocket.readable.getReader();
  const controller = {
    async 停止并刷新() {
      stopped = true;
      if (pendingSend) await pendingSend;
    }
  };
  if (remoteConnWrapper) remoteConnWrapper.downlinkController = controller;
  remoteSocket.closed?.catch?.(() => {});
  try {
    while (!stopped && active()) {
      const {value, done} = await reader.read();
      if (done || stopped || !active()) break;
      if (!value?.byteLength) continue;
      hasData = true;
      let chunk = value;
      if (headerPending) {
        headerPending = false;
        const header = typeof headerData === 'function' ? headerData() : headerData;
        if (header?.byteLength) {
          chunk = new Uint8Array(header.byteLength + value.byteLength);
          chunk.set(header);
          chunk.set(value, header.byteLength);
        }
      }
      if (webSocket.readyState !== WebSocket.OPEN) throw new Error('WebSocket closed');
      // Native send is synchronous. Adapters (SS/gRPC) may return a promise.
      pendingSend = webSocket.send(chunk);
      if (pendingSend && typeof pendingSend.then === 'function') await pendingSend;
      pendingSend = null;
    }
  } catch (err) {
    readError = err;
  } finally {
    if (remoteConnWrapper?.downlinkController === controller)
      remoteConnWrapper.downlinkController = null;
    try { await reader.cancel(); } catch {}
    try { reader.releaseLock(); } catch {}
    try { remoteSocket.close(); } catch {}
  }
  if (!active() || stopped) return;
  // Retry only a connection that never delivered data; never replay a stream.
  if (!hasData && retryFunc && webSocket.readyState === WebSocket.OPEN) {
    try { await retryFunc(); return; } catch (err) { readError = err; }
  }
  if (readError) log(`[TCP downlink] ${readError.message || readError}`);
  closeSocketQuietly(webSocket);
}
