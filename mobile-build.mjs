/* Build a deterministic static snapshot for Capacitor's webDir.
   During early beta, capacitor.config.json points to the existing HTTPS server.
   Before App Store release replace remote-only mode with reviewed native integration. */
import {mkdir,copyFile,rm} from "node:fs/promises";
import {join} from "node:path";
const files=[
 "index.html","styles.css","themes.css","ai-engine.css",
 "sonic-atelier.css","comic-flow.css","comic-variants.css",
 "flow-challenge.css","rap-flow.css","platform.css",
 "theme-engine.js","sonic-atelier.js","rhyme-fallback.js",
 "rhyme-previews.js","app.js","platform.js",
 "flow-scoring.js","flow-challenge.js","rap-audio.js","rap-flow.js"
];
await rm("www",{recursive:true,force:true});
await mkdir("www",{recursive:true});
for(const file of files) await copyFile(file,join("www",file));
console.log("Copied",files.length,"Reimflow frontend assets to www/");
