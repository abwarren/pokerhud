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
  
  function getAllPlayers(){
    const players=[];
    const seats=document.querySelectorAll('sg-poker-table-seat');
    console.log('[N4P-DEBUG] Found '+seats.length+' seat elements');
    
    let seatNum=0;
    for(const seat of seats){
      seatNum++;
      const seen=new Set();
      const hand=[];
      const cards=seat.querySelectorAll('.single-cart-view-p');
      console.log('[N4P-DEBUG] Seat '+seatNum+': '+cards.length+' card elements');
      
      for(const el of cards){
        const cls=el.getAttribute('class')||'';
        const c=tok(cls);
        console.log('[N4P-DEBUG]   Card class: "'+cls.substring(0,60)+'..." → token: '+c);
        if(c&&!seen.has(c)){
          seen.add(c);
          hand.push(c);
        }
      }
      
      console.log('[N4P-DEBUG] Seat '+seatNum+' hand: ['+hand.join(',')+'] ('+hand.length+' cards)');
      
      if(hand.length===4||hand.length===6){
        players.push(hand.join(''));
      }
    }
    
    console.log('[N4P-DEBUG] Total valid players: '+players.length);
    return players;
  }
  
  function getBoard(){
    const seen=new Set();
    const board=[];
    const boardEl=document.querySelector('sg-poker-board');
    if(!boardEl){
      console.log('[N4P-DEBUG] No board element found');
      return [];
    }
    
    const boardCards=boardEl.querySelectorAll('.single-cart-view-p');
    console.log('[N4P-DEBUG] Board has '+boardCards.length+' card elements');
    
    for(const el of boardCards){
      if(el.closest('sg-poker-table-seat'))continue;
      const c=tok(el.getAttribute('class')||'');
      if(c&&!seen.has(c)){
        seen.add(c);
        board.push(c);
      }
    }
    
    console.log('[N4P-DEBUG] Board cards: ['+board.join(',')+']');
    return board;
  }
  
  function send(text){
    const x=new XMLHttpRequest();
    x.open('POST',API);
    x.setRequestHeader('Content-Type','application/json');
    x.onload=function(){
      try{
        const d=JSON.parse(x.responseText);
        if(!d.dup){
          count++;
          console.log('[N4P] ✓ Snapshot #'+count+' saved');
        }
      }catch(e){}
    };
    x.send(JSON.stringify({text}));
  }
  
  function tick(){
    console.log('\n[N4P-DEBUG] ═══ TICK '+Date.now()+' ═══');
    const players=getAllPlayers();
    
    if(players.length<1){
      console.log('[N4P-DEBUG] No players found, skipping');
      return;
    }
    
    const board=getBoard();
    const lines=[...players];
    if(board.length>=3){
      lines.push(board.join(''));
    }
    
    const text=lines.join('\n');
    console.log('[N4P-DEBUG] Final snapshot:\n'+text);
    
    if(text===last){
      console.log('[N4P-DEBUG] Same as last, skipping send');
      return;
    }
    
    last=text;
    send(text);
  }
  
  window._n4p=setInterval(tick,3000); // Slower for debugging
  tick();
  console.log('%c[N4P] DEBUG MODE v3.1 running - check console for detail','color:#0f0;font-weight:bold');
})();
