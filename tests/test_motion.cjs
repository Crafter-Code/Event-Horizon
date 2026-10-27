const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync('field-renderer.js','utf8'),context);
let now=0;const motion=context.window.EHField.createMotion(()=>now);
const frame=(id,x)=>({frame_id:id,time:id*.1,period:1,in_play:true,players:[{team:0,number:7,x,y:20}],ball:[x,20]});
motion.push(frame(0,10),'a');
for(let i=1;i<=4;i++){now=i*800;motion.push(frame(i,10+i),'a');motion.sample();}
const positions=[];
for(let t=now;t<=now+500;t+=16)positions.push(motion.sample(t).players[0].x);
assert(new Set(positions).size>20,'Movement must continue between slow network frames');
assert(positions.every((x,i)=>!i||x>=positions[i-1]),'Playback must never move backwards');
assert(positions.every(x=>x<=14),'Never predict beyond confirmed positions');
now+=1000;motion.push(frame(0,40),'b');assert.equal(motion.sample().players[0].x,40);
now+=100;motion.push({...frame(1,41),period:2},'b');assert.equal(motion.sample().players[0].x,41);
motion.reset();assert.equal(motion.sample(),null);
console.log('Motion buffering checks passed');
