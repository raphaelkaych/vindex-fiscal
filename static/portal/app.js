/* Interação local da interface. Nenhum dado de formulário é persistido no navegador. */
(() => {
 'use strict';
 document.documentElement.classList.add('js');
 const status=document.querySelector('[data-action-status]');
 const announce=message=>{if(status)status.textContent=message;};
 const toggle=document.querySelector('[data-mobile-toggle]');
 const sidebar=document.querySelector('#sidebar');
 const closeButton=document.querySelector('[data-mobile-close]');
 const backdrop=document.querySelector('[data-menu-backdrop]');
 const background=document.querySelector('[data-menu-background]');
 const mobile=window.matchMedia('(max-width: 760px)');
 let menuOpen=false;
 const focusable=()=>sidebar?Array.from(sidebar.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')).filter(el=>!el.closest('[hidden],[inert]')&&el.getClientRects().length):[];
 const setMenu=(open,restoreFocus=false)=>{
  if(!sidebar||!toggle)return;
  const hadFocus=sidebar.contains(document.activeElement);
  menuOpen=Boolean(open&&mobile.matches);
  document.body.classList.toggle('menu-open',menuOpen);
  toggle.setAttribute('aria-expanded',String(menuOpen));
  toggle.setAttribute('aria-label',menuOpen?'Fechar menu':'Abrir menu');
  if(backdrop)backdrop.hidden=!menuOpen;
  if(background)background.inert=menuOpen;
  sidebar.inert=Boolean(mobile.matches&&!menuOpen);
  if(mobile.matches&&!menuOpen)sidebar.setAttribute('aria-hidden','true');
  else sidebar.removeAttribute('aria-hidden');
  if(menuOpen){
   sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');sidebar.setAttribute('aria-label','Navegação principal');
   (closeButton||focusable()[0])?.focus();
  }else{
   sidebar.removeAttribute('role');sidebar.removeAttribute('aria-modal');sidebar.removeAttribute('aria-label');
   if(mobile.matches&&(restoreFocus||hadFocus))toggle.focus({preventScroll:true});
   else if(!mobile.matches&&hadFocus&&document.activeElement===closeButton)focusable()[0]?.focus();
  }
 };
 toggle?.addEventListener('click',()=>setMenu(!menuOpen,true));
 closeButton?.addEventListener('click',()=>setMenu(false,true));
 backdrop?.addEventListener('click',()=>setMenu(false,true));
 sidebar?.querySelectorAll('a[href]').forEach(link=>link.addEventListener('click',()=>{if(menuOpen)setMenu(false,true);}));
 document.addEventListener('keydown',event=>{
  if(!menuOpen)return;
  if(event.key==='Escape'){event.preventDefault();setMenu(false,true);return;}
  if(event.key!=='Tab')return;
  const items=focusable();
  if(!items.length){event.preventDefault();return;}
  const first=items[0],last=items[items.length-1];
  if(event.shiftKey&&(document.activeElement===first||!sidebar.contains(document.activeElement))){event.preventDefault();last.focus();}
  else if(!event.shiftKey&&(document.activeElement===last||!sidebar.contains(document.activeElement))){event.preventDefault();first.focus();}
 });
 if(mobile.addEventListener)mobile.addEventListener('change',()=>setMenu(false));
 else mobile.addListener(()=>setMenu(false));
 setMenu(false);
 document.querySelectorAll('[data-auto-submit]').forEach(input=>input.addEventListener('change',()=>input.form?.requestSubmit()));

 const pending=new Map();
 const resetForms=()=>{
  const hadPending=pending.size>0;
  pending.forEach((buttons,form)=>{
   form.removeAttribute('aria-busy');form.classList.remove('is-submitting');
   buttons.forEach(({button,html,ariaDisabled})=>{
    if(button.tagName!=='INPUT')button.innerHTML=html;
    if(ariaDisabled===null)button.removeAttribute('aria-disabled');else button.setAttribute('aria-disabled',ariaDisabled);
   });
  });pending.clear();
  if(hadPending)announce('Página pronta para continuar.');
 };
 document.addEventListener('submit',event=>{
  const form=event.target;
  if(!(form instanceof HTMLFormElement)||event.defaultPrevented)return;
  if(pending.has(form)){event.preventDefault();return;}
  if(form.dataset.confirm&&!window.confirm(form.dataset.confirm)){event.preventDefault();return;}
  if(form.target&&form.target!=='_self')return;
  const method=(form.method||'get').toLowerCase();
  const importing=form.enctype==='multipart/form-data';
  const submitter=event.submitter;
  const label=submitter?.dataset.loadingLabel||form.dataset.loadingLabel||(method==='get'?'Filtrando…':importing?'Importando…':'Salvando…');
  const buttons=Array.from(form.querySelectorAll('button[type="submit"],button:not([type]),input[type="submit"]'));
  pending.set(form,buttons.map(button=>({button,html:button.innerHTML,ariaDisabled:button.getAttribute('aria-disabled')})));
  form.setAttribute('aria-busy','true');form.classList.add('is-submitting');
  buttons.forEach(button=>{
   // Nunca usa disabled nem altera value: preserva o submitter e todos os campos enviados.
   button.setAttribute('aria-disabled','true');
   if(button.tagName!=='INPUT'&&(!submitter||button===submitter))button.textContent=label;
  });
  announce(label+' Aguarde a conclusão.');
 });
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('button,input[type="submit"]');
  if(button&&pending.has(button.form)&&button.type==='submit')event.preventDefault();
 },true);
 window.addEventListener('pageshow',resetForms);

 const copying=new WeakSet();
 document.querySelectorAll('[data-copy-target]').forEach(button=>{
  button.hidden=false;
  button.addEventListener('click',async()=>{
   if(copying.has(button))return;
   const target=document.getElementById(button.dataset.copyTarget.replace(/^#/,''));
   if(!target){announce('Conteúdo indisponível para copiar.');return;}
   const value='value' in target?target.value:target.textContent.trim();
   const label=button.querySelector('[data-copy-label]')||button;
   const original=label.textContent;
   copying.add(button);button.setAttribute('aria-disabled','true');
   try{
    if(!navigator.clipboard?.writeText)throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(value);
    label.textContent='Copiado';button.classList.add('is-copied');announce('Copiado para a área de transferência.');
    window.setTimeout(()=>{label.textContent=original;button.classList.remove('is-copied');},1800);
   }catch(_){
    target.focus({preventScroll:true});
    if(typeof target.select==='function')target.select();
    else if(window.getSelection&&document.createRange){const range=document.createRange();range.selectNodeContents(target);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}
    announce('Não foi possível copiar automaticamente. Conteúdo selecionado: use Ctrl+C ou a opção Copiar do dispositivo.');
   }finally{copying.delete(button);button.removeAttribute('aria-disabled');}
  });
 });
 document.querySelectorAll('input[type="file"]').forEach(input=>{
  const zone=input.closest('[data-drop-zone]');
  let summary=zone?.querySelector('[data-file-names]');
  if(!summary){summary=document.createElement('p');summary.className='file-summary';summary.setAttribute('aria-live','polite');input.insertAdjacentElement('afterend',summary);}
  const update=()=>{summary.textContent=input.files.length?Array.from(input.files).map(file=>file.name).join(' · '):'Nenhum arquivo selecionado.';};
  input.addEventListener('change',update);update();
  if(!zone)return;
  ['dragenter','dragover'].forEach(type=>zone.addEventListener(type,event=>{event.preventDefault();zone.classList.add('dragging');}));
  ['dragleave','drop'].forEach(type=>zone.addEventListener(type,event=>{event.preventDefault();zone.classList.remove('dragging');}));
  zone.addEventListener('drop',event=>{
   if(!event.dataTransfer?.files.length)return;
   if(!input.multiple&&event.dataTransfer.files.length>1){summary.textContent='Selecione um arquivo por vez.';return;}
   try{input.files=event.dataTransfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
   catch(_){summary.textContent='Use o botão Escolher arquivos para selecionar os documentos.';}
  });
 });
 const errors=Array.from(document.querySelectorAll('form .errorlist')).filter(list=>list.textContent.trim());
 errors.forEach((list,index)=>{
  if(!list.id)list.id='validation-errors-'+index;
  list.setAttribute('tabindex','-1');
  const group=list.closest('.form-field');
  let fields=group?Array.from(group.querySelectorAll('input:not([type="hidden"]),select,textarea')):[];
  if(!fields.length&&list.id.endsWith('_error')){const field=document.getElementById(list.id.slice(0,-6));if(field)fields=[field];}
  fields.forEach(field=>{
   field.setAttribute('aria-invalid','true');
   const described=new Set((field.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean));described.add(list.id);
   field.setAttribute('aria-describedby',Array.from(described).join(' '));
  });
  list.closest('form')?.classList.add('has-errors');
 });
 if(errors.length){
  announce('Confira os campos sinalizados. Os dados não sensíveis preenchidos foram mantidos; selecione novamente arquivos e informe senhas quando necessário.');
  const field=errors[0].closest('.form-field')?.querySelector('input:not([type="hidden"]),select,textarea');
  (field||errors[0]).focus();
 }
 document.querySelectorAll('.table-scroll').forEach(table=>{
  table.setAttribute('tabindex','0');table.setAttribute('role','region');
  if(!table.hasAttribute('aria-label'))table.setAttribute('aria-label',(table.closest('.panel')?.querySelector('h2')?.textContent||'Documentos')+' — tabela com rolagem horizontal');
 });
})();
