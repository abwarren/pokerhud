(function(){
  'use strict';

  // === N4P LOAD GUARD ===
  if (window._n4p) {
    console.log("[N4P] clearing old instance — upgrading");
    clearInterval(window._n4p);
    window._n4p=null;
  }

  const API='https://nuts4poker.com/collector/save';
  let last='',count=0;

  // Page visibility — skip ticks when tab hidden
  let isPageVisible = !document.hidden;
  document.addEventListener('visibilitychange', function(){
    isPageVisible = !document.hidden;
    console.log('[N4P] Page ' + (isPageVisible ? 'visible - resuming' : 'hidden - pausing'));
  });

  // Trace ring buffer
  window.__n4pTrace=window.__n4pTrace||[];
  function n4pTrace(event,extra){
    var row={ts:new Date().toISOString(),event:event};
    for(var k in extra)row[k]=extra[k];
    window.__n4pTrace.push(row);
    if(window.__n4pTrace.length>200)window.__n4pTrace.shift();
    console.log('[N4P-TRACE]',row);
  }

  // Iframe detection
  function getRootDoc(){
    var frames=document.querySelectorAll('iframe');
    for(var i=0;i<frames.length;i++){
      var src=String(frames[i].src||'');
      if(src.indexOf('skillgames')!==-1||src.indexOf('18751019')!==-1||src.indexOf('187510019')!==-1){
        try{
          var doc=frames[i].contentDocument||(frames[i].contentWindow&&frames[i].contentWindow.document);
          if(doc)return doc;
        }catch(e){}
      }
    }
    return document;
  }

  // Parse PokerBet card CSS class
  function parseCard(cls){
    if(!cls)return null;
    var tokens=(cls).split(/\s+/).filter(function(t){
      return /^icon-layer2_([hdcs])(a|k|q|j|10|[2-9])_p-c-d$/i.test(t);
    });
    if(!tokens.length)return null;
    var m=tokens[tokens.length-1].match(/^icon-layer2_([hdcs])(a|k|q|j|10|[2-9])_p-c-d$/i);
    if(!m)return null;
    var rankMap={a:'A',k:'K',q:'Q',j:'J','10':'T'};
    return (rankMap[m[2].toLowerCase()]||m[2].toUpperCase())+m[1].toLowerCase();
  }

  function getCardsFromElement(el){
    if(!el)return [];
    var cards=[],seen=new Set();
    var cardEls=el.querySelectorAll('.single-cart-view-p');
    for(var i=0;i<cardEls.length;i++){
      var c=parseCard(cardEls[i].getAttribute('class')||'');
      if(c&&!seen.has(c)){seen.add(c);cards.push(c);}
    }
    return cards;
  }

  function extractPosition(className){
    var m=String(className||'').match(/position-(\d+)/);
    return m?Number(m[1]):null;
  }

  // Get board cards
  function getBoard(){
    var doc=getRootDoc();
    var boardEl=doc.querySelector('sg-poker-board');
    if(boardEl){
      var cards=[],seen=new Set();
      var cardEls=boardEl.querySelectorAll('.single-cart-view-p');
      for(var i=0;i<cardEls.length;i++){
        if(cardEls[i].closest('sg-poker-table-seat')||cardEls[i].closest('.player-mini-container-p'))continue;
        var c=parseCard(cardEls[i].getAttribute('class')||'');
        if(c&&!seen.has(c)){seen.add(c);cards.push(c);}
      }
      if(cards.length>=3)return cards.join('');
    }
    var containers=doc.querySelectorAll('.carts-container-p');
    for(var j=0;j<containers.length;j++){
      if(!containers[j].closest('.player-mini-container-p')){
        var fc=getCardsFromElement(containers[j]);
        if(fc.length>=3)return fc.join('');
      }
    }
    return null;
  }

  // Scan ALL visible seats RIGHT NOW — no accumulation, just what's on screen
  function scanCurrentSnapshot(){
    var doc=getRootDoc();
    var seatEls=doc.querySelectorAll('sg-poker-table-seat');
    if(!seatEls.length){
      seatEls=doc.querySelectorAll('.player-mini-container-p');
    }

    var hands=[];
    for(var i=0;i<seatEls.length;i++){
      var seat=seatEls[i];
      var cards=[];
      var cardsContainer=seat.querySelector('.carts-container-p');
      if(cardsContainer){
        cards=getCardsFromElement(cardsContainer);
      }else{
        cards=getCardsFromElement(seat);
      }
      if(cards.length>=4&&cards.length<=7){
        hands.push(cards.join(''));
      }
    }
    return hands;
  }

  // Send snapshot — each tick sends exactly what's visible, no accumulation
  function send(hands, board){
    if(hands.length<2){
      console.log('[N4P] skip: only '+hands.length+' hands visible');
      return;
    }

    var lines=hands.slice();
    if(board)lines.push('BOARD:'+board);
    var text=lines.join('\n');

    // Dedup only — no debounce
    if(text===last)return;
    last=text;

    n4pTrace('post_begin',{handCount:hands.length,hasBoard:!!board});
    count++;
    console.log('[N4P] Snapshot #'+count+' ('+hands.length+' hands'+(board ? ', board='+board : '')+'):\n'+text);

    var x=new XMLHttpRequest();
    x.open('POST',API);
    x.setRequestHeader('Content-Type','application/json');
    x.onload=function(){
      n4pTrace('post_ok',{status:x.status});
      try{
        var d=JSON.parse(x.responseText);
        if(d.dup){
          console.log('[N4P] dup snapshot (backend dedup)');
        }
      }catch(e){
        console.error('[N4P] Response error:',x.responseText);
      }
    };
    x.onerror=function(){
      n4pTrace('post_fail',{error:'network_error'});
      console.error('[N4P] Network error');
    };
    x.send(JSON.stringify({text:text}));
  }

  // Main tick — no accumulation, no debounce, no rate limit
  function tick(){
    if(!isPageVisible)return;
    var hands=scanCurrentSnapshot();
    var board=getBoard();
    n4pTrace('scan',{handCount:hands.length,boardCards:board?board.length/2:0});
    send(hands,board);
  }

  // Public API
  window._n4pState=function(){
    var h=scanCurrentSnapshot();
    return{hands:h,board:getBoard(),count:count};
  };

  window._n4p_injected=true;
  window._n4p_buildSnapshot=function(){
    var s=window._n4pState();
    return{hands:s.hands,board:s.board,count:s.count};
  };

  window._n4p=setInterval(tick,1500);
  tick();
  console.log('[N4P] v8.1 loaded — no accumulation, no debounce, each snapshot sent raw');
})();
