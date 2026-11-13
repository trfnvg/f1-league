/* Read-only showroom: there are no purchases or wallet writes on this page. */
(() => {
  "use strict";
  const root=document.getElementById("casino-shop");if(!root)return;
  const $=id=>document.getElementById(`shop-${id}`);
  const products=new Map(JSON.parse($("products").textContent).map(p=>[p.key,p]));
  $("balance").textContent=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(JSON.parse($("wallet").textContent)/100);
  const dialog=$("product-dialog"),tip=$("tooltip"),hover=matchMedia("(hover:hover) and (pointer:fine)");
  let active=null,tipTarget=null;
  function hideTip(){tip.hidden=true;tipTarget?.removeAttribute("aria-describedby");tipTarget=null;}
  function showTip(button){
    if(!hover.matches||dialog.open)return;
    const p=products.get(button.dataset.product);if(!p)return;
    hideTip();tipTarget=button;button.setAttribute("aria-describedby",tip.id);
    $("tip-kind").textContent=p.kind;$("tip-title").textContent=p.name;$("tip-price").textContent=p.price;$("tip-copy").textContent=p.description;
    tip.hidden=false;
    const rect=button.getBoundingClientRect(),box=tip.getBoundingClientRect();
    tip.style.left=`${Math.max(12,Math.min(innerWidth-box.width-12,rect.left+rect.width/2-box.width/2))}px`;
    tip.style.top=`${Math.max(12,Math.min(innerHeight-box.height-12,rect.top-box.height-10))}px`;
  }
  function close(){dialog.close();active?.focus({preventScroll:true});}
  for(const button of root.querySelectorAll("[data-product]")){
    button.addEventListener("pointerenter",()=>showTip(button));button.addEventListener("pointerleave",hideTip);
    button.addEventListener("focus",()=>showTip(button));button.addEventListener("blur",hideTip);
    button.addEventListener("click",()=>{
      const p=products.get(button.dataset.product);if(!p)return;
      hideTip();active=button;
      for(const [id,key] of [["name","name"],["kind","kind"],["price","price"],["description","description"],["rule","rule"]])$("detail-"+id).textContent=p[key];
      $("detail-art").className=`shop-detail-art shop-item-art shop-item-${p.key}`;
      dialog.showModal();$("close").focus({preventScroll:true});
    });
  }
  $("close").addEventListener("click",close);$("done").addEventListener("click",close);
  dialog.addEventListener("click",e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
  dialog.addEventListener("cancel",()=>{hideTip();});
  window.addEventListener("scroll",hideTip,{passive:true});window.addEventListener("resize",hideTip);
  document.addEventListener("keydown",e=>{if(e.key==="Escape")hideTip();});
})();
