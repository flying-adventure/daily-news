// 오늘의 고양이 6마리 (이미지 생성으로 만든 픽셀 고양이, cats/<id>-<자세>.png)
const CATS = [
  {id:'gureum', name:'구름', kind:'회색이'},
  {id:'jjajang', name:'짜장', kind:'까망이'},
  {id:'tuxi', name:'턱시', kind:'턱시도'},
  {id:'samsun', name:'삼순이', kind:'삼색이'},
  {id:'shampoo', name:'샴푸', kind:'샴'},
  {id:'dubu', name:'두부', kind:'흰둥이'},
];
const POSES = ['sleep', 'sit', 'walkA', 'walkB'];
// 그림 폴더 = 이 스크립트 옆 cats/ (페이지 주소와 무관하게)
const CAT_DIR = new URL('cats/', document.currentScript.src).href;
// 자세별 이미지 주소 (미리 불러와서 자세 바뀔 때 깜빡임 방지)
const catImages = cat => Object.fromEntries(POSES.map(k => { const src = `${CAT_DIR}${cat.id}-${k}.png`; new Image().src = src; return [k, src]; }));
// 오늘 날짜로 고르는 고양이 (같은 날엔 같은 고양이)
function todayCat(){
  const d = new Date(), key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
  let h = 7; for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % CATS.length;
}
function pixURL(rows, pal){
  const c = document.createElement('canvas'); c.width = rows[0].length; c.height = rows.length;
  const g = c.getContext('2d');
  rows.forEach((row, y) => [...row].forEach((ch, x) => { if (pal[ch]) { g.fillStyle = pal[ch]; g.fillRect(x, y, 1, 1); } }));
  return { src: c.toDataURL(), w: c.width, h: c.height };
}
// 탭 아이콘 (a=초록, r=분홍)
const ICON_PAL = { k:'#050706', a:'#4ade80', r:'#ff6b8a', w:'#cfdad4' };
const ICONS = {
  saved: pixURL(['.kkkkkkk.','kaaaaaaak','kakkkkkak','kaaaaaaak','kaaaaaaak','kaaaaaaak','kaaaaaaak','kwwwwwwwk','kkkkkkkkk'], ICON_PAL),
  digest: pixURL(['kkkkkkkkkk','kwkwwwwkwk','kwwkwwkwwk','kwwwkkwwwk','kwwwwwwrrk','kwwwwwwrrk','kwwwwwwwwk','kkkkkkkkkk'], ICON_PAL),
  liked: pixURL(['.kkk.kkk.','krrrkrrrk','krwrrrrrk','krrrrrrrk','.krrrrrk.','..krrrk..','...krk...','....k....'], ICON_PAL),
};
