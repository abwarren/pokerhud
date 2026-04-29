(function(){
  clearInterval(window._n4p);
  window._n4p=null;
  
  const API='https://nuts4poker.com/collector/save';
  let last='',count=0;
  
  function tok(cls){
    const h=(cls||'').split(/\s+/).filter(t=>/^icon-layer2_([hdcs])(a|k|q|j|10|[2-9])_p-c-d$/i.test(t));
    if(!h.length)return null;
    const m=h[h.length-1].match(/^icon-layer2_([hdcs])(a|k|q|j|10|[2-9])_p-c-d$/i);
    return ({a:'A',k:'K',q:'Q',j:'J','10':'T'}[m[2].toLowerCase()]||m[2]).toUpperCase()+m[1].toLowerCase();
  }
  
  // Get table name from current window/tab
  function getTableName(){
    const titleEl=document.querySelector('title');
    if(titleEl){
      const m=titleEl.textContent.match(/PLO[46]?\s*[-–]\s*([^-–|]+)/i);
      if(m)return m[1].trim();
    }
    // Fallback: check for table identifier in DOM
    const tableLabel=document.querySelector('.table-name, [class*="table-title"], [class*="room-name"]');
    if(tableLabel)return tableLabel.textContent.trim();
    return 'UNKNOWN';
  }
  
  // Get hero hand from current table
  function getHero(){
    for(const seat of document.querySelectorAll('sg-poker-table-seat')){
      const seen=new Set(),out=[];
      for(const el of seat.querySelectorAll('.single-cart-view-p')){
        const c=tok(el.getAttribute('class')||'');
        if(c&&!seen.has(c)){seen.add(c);out.push(c);}
      }
      if(out.length>=4)return out; // Found hero
    }
    return[];
  }
  
  // Get board
  function getBoard(){
    const seen=new Set(),out=[];
    const boardEl=document.querySelector('sg-poker-board');
    if(!boardEl)return[];
    for(const el of boardEl.querySelectorAll('.single-cart-view-p')){
      if(el.closest('sg-poker-table-seat'))continue;
      const c=tok(el.getAttribute('class')||'');
      if(c&&!seen.has(c)){seen.add(c);out.push(c);}
    }
    return out;
  }
  
  function send(text){
    const x=new XMLHttpRequest();
    x.open('POST',API);
    x.setRequestHeader('Content-Type','application/json');
    x.onload=function(){
      try{
        const d=JSON.parse(x.responseText);
        if(!d.dup){count++;console.log('[N4P] #'+count+' saved');}
      }catch(e){}
    };
    x.send(JSON.stringify({text}));
  }
  
  function tick(){
    const table=getTableName();
    const hero=getHero();
    if(hero.length<4)return;
    
    const board=getBoard();
    const lines=['TABLE:'+table,hero.join('')];
    if(board.length>=3)lines.push(board.join(''));
    
    const text=lines.join('\n');
    if(text===last)return;
    last=text;
    send(text);
  }
  
  window._n4p=setInterval(tick,1500);
  tick();
  console.log('[N4P] Multi-table v4.0 - emits TABLE:name + hero + board');
})();
