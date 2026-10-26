/** Render the current display PDF to 2560x1440 PNGs, then place one image per
 * slide. Notes come from slides.json; slide content is intentionally flattened.
 * Missing PDF/pages, rasterization or validation failures stop publication.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies');
const python=process.env.RUNTIME_PYTHON||path.join(runtime,'python/bin/python3');
const modules=process.env.ARTIFACT_NODE_MODULES||path.join(runtime,'node/node_modules');
process.env.RUNTIME_NODE_MODULES ||= modules;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(modules,'@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const skill=process.env.PRESENTATION_SKILL_DIR||path.join(os.homedir(),'.codex/plugins/cache/openai-primary-runtime/presentations/26.1024.11018/skills/presentations');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const spec=JSON.parse(await fs.readFile(path.join(root,'presentations/01-opening/ppt/slides.json'),'utf8'));
const build=path.join(root,'.build/image-slides');await fs.mkdir(build,{recursive:true});
const source=path.join(root,'presentations/01-opening/ppt/第11组_开题展示.pdf');
execFileSync(python,['-c',`import sys,pypdfium2 as p\nfrom pathlib import Path\ndoc=p.PdfDocument(sys.argv[1]);assert len(doc)==int(sys.argv[3])\nfor i,page in enumerate(doc):\n im=page.render(scale=2560/page.get_width()).to_pil().convert('RGB');assert im.size==(2560,1440),im.size;im.save(Path(sys.argv[2])/f'slide-{i+1:02}.png')`,source,build,String(spec.slides.length)]);
const presentation=Presentation.create({slideSize:{width:1280,height:720}});
for(const [i,s] of spec.slides.entries()){
 const slide=presentation.slides.add();const b=await fs.readFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`));
 slide.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:`第${i+1}页：${s.title}`,fit:'contain',position:{left:0,top:0,width:1280,height:720}});
 slide.speakerNotes.text=s.notes;
}
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(presentation)).save(candidate);
const validated=path.join(root,'.build/validated');await fs.mkdir(validated,{recursive:true});
const checked=path.join(validated,`image-checked-${Date.now()}.pptx`);
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:checked,pythonExecutable:python,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000'],explicitTotalSlideCount:spec.slides.length,
 requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],verifyArtifactToolImport:true,receiptPath:path.join(build,`validation-${Date.now()}.json`)});
const final=path.join(root,`presentations/01-opening/ppt/第11组_开题展示_${spec.version}_纯图片版.pptx`);
await fs.copyFile(checked,final+'.tmp');await fs.rename(final+'.tmp',final);
console.log(final);
