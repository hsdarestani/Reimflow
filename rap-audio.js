/* Reimflow recorded audio normalization.
 * Browser MediaRecorder WebM often omits duration, making Chrome display
 * fictitious lengths (e.g. 05:57 for a 20-second recording).
 * Decode locally, downsample to 16 kHz mono, encode a standard PCM WAV.
 * No upload, additional network dependency or storage.
 */
(function(root){
  "use strict";
  const RATE=16000;
  function encodeWav(channels,sampleRate){
    if(!channels?.length||!Number.isFinite(sampleRate)||sampleRate<8000)throw new Error("INVALID_PCM");
    const length=channels[0].length, samples=Math.max(1,Math.round(length*RATE/sampleRate));
    if(samples>RATE*36)throw new Error("AUDIO_TOO_LONG");
    const buffer=new ArrayBuffer(44+samples*2),view=new DataView(buffer);
    const ascii=(offset,value)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
    ascii(0,"RIFF");view.setUint32(4,36+samples*2,true);ascii(8,"WAVE");
    ascii(12,"fmt ");view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
    view.setUint32(24,RATE,true);view.setUint32(28,RATE*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
    ascii(36,"data");view.setUint32(40,samples*2,true);
    const ratio=sampleRate/RATE;
    for(let i=0;i<samples;i++){
      const pos=i*ratio,low=Math.min(length-1,Math.floor(pos)),high=Math.min(length-1,low+1);
      let avg=0;
      for(const channel of channels)avg+=(channel[low]||0)+(channel[high]-channel[low]||0)*(pos-low);
      const sample=Math.max(-1,Math.min(1,avg/channels.length));
      view.setInt16(44+i*2,sample<0?Math.round(sample*32768):Math.round(sample*32767),true);
    }
    return {blob:new Blob([buffer],{type:"audio/wav"}),durationSeconds:samples/RATE,sampleRate:RATE};
  }
  async function normalize(blob){
    const Context=root.AudioContext||root.webkitAudioContext;
    if(!Context)throw new Error("AUDIO_DECODE_UNAVAILABLE");
    const context=new Context();
    try{
      const input=await blob.arrayBuffer();
      const decoded=await context.decodeAudioData(input);
      const channels=[];
      for(let i=0;i<decoded.numberOfChannels;i++)channels.push(decoded.getChannelData(i));
      return encodeWav(channels,decoded.sampleRate);
    }finally{
      try{await context.close()}catch{}
    }
  }
  root.ReimflowRapAudio=Object.freeze({normalize,encodeWav,RATE});
})(typeof window!=="undefined"?window:globalThis);
