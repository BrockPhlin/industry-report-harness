/**
 * Editable deck builder: slides.json -> native shapes/tables -> PPTX + previews.
 * Required runtime: @oai/artifact-tool and @napi-rs/canvas. No business logic is
 * executed here. Missing fonts, malformed geometry and export errors fail the
 * build. The private candidate is validated before the final file is written.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const skill=process.env.PRESENTATION_SKILL_DIR || path.join(os.homedir(),'.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations');
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const modules = process.env.ARTIFACT_NODE_MODULES || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
// Validation runs a child process which resolves the same SDK independently.
process.env.RUNTIME_NODE_MODULES ||= modules;
const entry = process.env.ARTIFACT_TOOL_MODULE || path.join(modules, '@oai/artifact-tool/dist/artifact_tool.mjs');
const {Presentation, PresentationFile} = await import(pathToFileURL(entry).href);
const require = createRequire(path.join(modules, '../package.json'));
const {GlobalFonts} = require('@napi-rs/canvas');
for (const [filename, alias] of [['LXGWWenKai-Regular.ttf','LXGW WenKai'], ['LXGWWenKai-Medium.ttf','LXGW WenKai Medium'], ['SmileySans-Oblique.ttf','Smiley Sans Oblique']]) {
  if (!GlobalFonts.registerFromPath(path.join(root,'assets/fonts',filename),alias)) throw new Error(`Font registration failed: ${filename}`);
}

const spec = JSON.parse(await fs.readFile(path.join(root,'presentations/01-opening/ppt/slides.json'),'utf8'));
const build = path.join(root,'.build/slides');
await fs.mkdir(build,{recursive:true});
const presentation = Presentation.create({slideSize:{width:1280,height:720}});
const BLUE='#003F88', INK='#233042', MUTED='#60728C', PALE='#ECF3FA';

function box(slide,x,y,w,h,fill='none',line='none',width=0) {
  return slide.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width,style:'solid'}});
}
function text(slide,item) {
  const shape=slide.shapes.add({geometry:'textbox',position:{left:item.x,top:item.y,width:item.w,height:item.h},fill:'none',line:{fill:'none',width:0}});
  shape.text=item.text;
  shape.text.style={fontSize:item.size,typeface:item.font==='title'?'Smiley Sans Oblique':'LXGW WenKai',bold:item.bold||false,color:item.color||INK,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};
  return shape;
}
async function picture(slide,item) {
  const bytes=await fs.readFile(path.join(root,item.path));
  slide.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:path.basename(item.path),fit:'contain',position:{left:item.x,top:item.y,width:item.w,height:item.h}});
}
function table(slide,item) {
  const n=item.rows.length, m=item.rows[0].length;
  if(item.rows.some(row=>row.length!==m)) throw new Error('Inconsistent slide table');
  const t=slide.tables.add({rows:n,columns:m,left:item.x,top:item.y,width:item.w,height:item.h,columnWidths:item.widths.map(v=>v*item.w),values:item.rows});
  t.borders.assign({style:'solid',fill:'#D9E1EB',width:.6});
  for(let r=0;r<n;r++) {
    t.rows[r].height=item.h/n;
    for(let c=0;c<m;c++) {
      const cell=t.getCell(r,c);
      cell.fill=r===0?PALE:'#FFFFFF';
      cell.text.style={fontSize:item.size,typeface:'LXGW WenKai',bold:r===0,color:r===0?BLUE:INK,verticalAlignment:'middle',insets:{left:10,right:10,top:6,bottom:6},wrap:'square',autoFit:'none'};
    }
  }
}
function flow(slide,item) {
  for(const [x1,y1,x2,y2] of item.edges) box(slide,Math.min(x1,x2),Math.min(y1,y2),Math.max(1.5,Math.abs(x2-x1)),Math.max(1.5,Math.abs(y2-y1)),BLUE);
  for(const [title,body,x,y,w,h] of item.nodes) {
    box(slide,x,y,w,h,PALE,BLUE,1);
    text(slide,{text:title,x:x+15,y:y+13,w:w-30,h:40,size:30,bold:true,color:BLUE});
    text(slide,{text:body,x:x+15,y:y+63,w:w-30,h:35,size:23});
  }
}
async function chart(slide,item) {
  const data=JSON.parse(await fs.readFile(path.join(root,item.data_path),'utf8')).chart;
  const native=slide.charts.add('bar',{
    position:{left:item.x,top:item.y,width:item.w,height:item.h},
    categories:data.categories,
    series:[{name:data.unit,values:data.values,fill:BLUE,points:[{idx:0,fill:BLUE},{idx:1,fill:'#AD5D23'}]}],
    hasLegend:false,
    barOptions:{direction:'column',grouping:'clustered',gapWidth:130},
    xAxis:{tickLabelPosition:'low',textStyle:{fontSize:23,fill:INK}},
    yAxis:{min:-.4,max:.2,majorUnit:.1,numberFormatCode:'0%',textStyle:{fontSize:20,fill:MUTED}},
    dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0%;-0.0%',textStyle:{fontSize:26,fill:INK}},
  });
  applyPresentationChartFont(native,{fontFamily:'LXGW WenKai'});
}

for(const [idx,specSlide] of spec.slides.entries()) {
  const slide=presentation.slides.add();
  slide.background.fill='#FFFFFF';
  if(idx===0) box(slide,65,330,1150,90,PALE);
  else {
    text(slide,{text:specSlide.title,x:60,y:27,w:1040,h:58,size:40,font:'title',color:BLUE});
    box(slide,60,89,1160,3,BLUE);
    text(slide,{text:specSlide.subtitle,x:65,y:100,w:1100,h:40,size:23,color:MUTED});
    await picture(slide,{path:'assets/brand/char_blue.png',x:1100,y:30,w:115,h:39});
  }
  for(const item of specSlide.items) {
    if(item.type==='text') text(slide,item);
    else if(item.type==='table') table(slide,item);
    else if(item.type==='flow') flow(slide,item);
    else if(item.type==='image') await picture(slide,item);
    else if(item.type==='box') box(slide,item.x,item.y,item.w,item.h,item.fill);
    else if(item.type==='chart') await chart(slide,item);
    else throw new Error(`Unknown slide item ${item.type}`);
  }
  text(slide,{text:`第11组 / 开题评阅稿 ${spec.version}`,x:65,y:682,w:1040,h:25,size:17,color:MUTED});
  text(slide,{text:`${String(idx+1).padStart(2,'0')} / ${spec.slides.length}`,x:1135,y:682,w:100,h:25,size:17,color:MUTED});
  slide.speakerNotes.text=specSlide.notes;
}

const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidate);
console.log(`Exported editable candidate: ${spec.slides.length} slides`);
for(const [idx,slide] of presentation.slides.items.entries()) {
  const png=await presentation.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${String(idx+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
  console.log(`Rendered slide ${idx+1}`);
}


const final=path.join(root,`presentations/01-opening/ppt/第11组_开题展示_${spec.version}.pptx`);
// The finalizer never overwrites a published output. Rebuild to a fresh private
// final and only then replace the repository draft atomically.
const checkedDir=path.join(root,'.build/validated');
await fs.mkdir(checkedDir,{recursive:true});
const checked=path.join(checkedDir,`checked-${Date.now()}.pptx`);
const tableOwners=spec.slides.flatMap((s,i)=>s.items.some(x=>x.type==='table')?[i+1]:[]);
const chartOwners=spec.slides.flatMap((s,i)=>s.items.some(x=>x.type==='chart')?[i+1]:[]);
const python=process.env.RUNTIME_PYTHON || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3');
const receipt=path.join(build,`validation-${Date.now()}.json`);
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:checked,
  pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],
  explicitTotalSlideCount:spec.slides.length,
  requiredNativeTableOwnerSlides:tableOwners,
  requiredNativeChartOwnerSlides:chartOwners,
  materializeLiteralChartWorkbooks:true,
  fontPolicy:{basis:'design',families:['LXGW WenKai','Smiley Sans Oblique']},
  verifyArtifactToolImport:true,
  receiptPath:receipt});
const nextFinal=final+'.tmp';
await fs.copyFile(checked,nextFinal);
await fs.rename(nextFinal,final);
await fs.copyFile(receipt,path.join(build,'validation.json'));
console.log(JSON.stringify({final,validation:result},null,2));
