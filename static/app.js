const input=document.getElementById("fileInput");
const dropzone=document.getElementById("dropzone");
const browseBtn=document.getElementById("browseBtn");
const analyseBtn=document.getElementById("analyseBtn");
const selected=document.getElementById("selectedFile");
const statusText=document.getElementById("statusText");
const progressWrap=document.getElementById("progressWrap");
const results=document.getElementById("results");
const toast=document.getElementById("toast");
let chosenFile=null;
let toastTimer;
function notify(message){toast.textContent=message;toast.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove("show"),2600);}
function formatBytes(bytes){return bytes<1024*1024?(bytes/1024).toFixed(0)+" KB":(bytes/(1024*1024)).toFixed(1)+" MB";}
function setFile(file){
  if(!file)return;
  const valid=/\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(file.name);
  if(!valid){notify("Choose a supported video format.");return;}
  if(file.size>350*1024*1024){notify("This video is larger than 350 MB.");return;}
  chosenFile=file;document.getElementById("fileName").textContent=file.name;document.getElementById("fileSize").textContent=formatBytes(file.size);
  selected.classList.remove("hidden");dropzone.classList.add("hidden");analyseBtn.disabled=false;statusText.textContent="Ready when you are.";
}
function clearFile(){chosenFile=null;input.value="";selected.classList.add("hidden");dropzone.classList.remove("hidden");analyseBtn.disabled=true;statusText.textContent="No video selected yet.";}
browseBtn.addEventListener("click",e=>{e.stopPropagation();input.click();});
dropzone.addEventListener("click",()=>input.click());
dropzone.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();input.click();}});
input.addEventListener("change",()=>setFile(input.files[0]));
document.getElementById("removeFile").addEventListener("click",clearFile);
["dragenter","dragover"].forEach(type=>dropzone.addEventListener(type,e=>{e.preventDefault();dropzone.classList.add("dragover");}));
["dragleave","drop"].forEach(type=>dropzone.addEventListener(type,e=>{e.preventDefault();dropzone.classList.remove("dragover");}));
dropzone.addEventListener("drop",e=>setFile(e.dataTransfer.files[0]));
analyseBtn.addEventListener("click",async()=>{
  if(!chosenFile)return;
  analyseBtn.disabled=true;progressWrap.classList.remove("hidden");statusText.textContent="Uploading and analysing…";
  document.getElementById("progressLabel").textContent="Extracting frames and reading visible text…";results.classList.add("hidden");
  const body=new FormData();body.append("video",chosenFile);
  try{
    const response=await fetch("/api/analyse",{method:"POST",body});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||"Analysis failed. Please try again.");
    renderReport(data);progressWrap.classList.add("hidden");results.classList.remove("hidden");statusText.textContent="Analysis complete.";
    results.scrollIntoView({behavior:"smooth",block:"start"});
  }catch(error){notify(error.message);progressWrap.classList.add("hidden");statusText.textContent="Something went wrong. Try again.";}
  finally{analyseBtn.disabled=false;}
});
function renderReport(data){
  document.getElementById("statFrames").textContent=data.summary.frames_scanned;
  document.getElementById("statText").textContent=data.summary.frames_with_text;
  document.getElementById("statIssues").textContent=data.summary.issues_found;
  document.getElementById("combinedText").textContent=data.combined_text||"No readable text was detected in the sampled frames.";
  document.getElementById("reportNotice").textContent=data.notice||"";
  const all=[];data.frames.forEach(frame=>frame.findings.forEach(item=>all.push({...item,timestamp:frame.timestamp,seconds:frame.seconds})));
  document.getElementById("findingCount").textContent=all.length+" finding"+(all.length===1?"":"s");
  const list=document.getElementById("findingsList");list.replaceChildren();
  if(!all.length){
    const empty=document.createElement("div");empty.className="empty-findings";
    empty.textContent=data.summary.frames_with_text?(data.language_check_available===false?"Text was extracted, but the language checker could not start on this server.":"No clear spelling or grammar suggestions were found. Give the extracted text a quick human review anyway."):"No text was confidently detected. Try a higher-resolution export or a clip with clearer text.";
    list.append(empty);return;
  }
  all.forEach(item=>{
    const card=document.createElement("article");card.className="finding";const top=document.createElement("div");top.className="finding-top";
    const time=document.createElement("span");time.className="timestamp-button";time.textContent=item.timestamp;time.title="Timestamp in original video";
    const kind=document.createElement("span");kind.className="finding-kind";kind.textContent=item.category;top.append(time,kind);
    const message=document.createElement("p");message.className="finding-message";message.textContent=item.message;
    const context=document.createElement("div");context.className="finding-context";context.textContent=item.context;card.append(top,message,context);
    if(item.suggestion){const suggestion=document.createElement("div");suggestion.className="suggestion";suggestion.textContent="Suggested: "+item.suggestion;card.append(suggestion);}
    list.append(card);
  });
}
document.getElementById("copyText").addEventListener("click",async()=>{
  const value=document.getElementById("combinedText").textContent;
  try{await navigator.clipboard.writeText(value);notify("Detected text copied.");}catch{notify("Clipboard access is unavailable in this browser.");}
});
function resetScan(){results.classList.add("hidden");progressWrap.classList.add("hidden");clearFile();window.scrollTo({top:0,behavior:"smooth"});}
document.getElementById("newScanBtn").addEventListener("click",resetScan);
