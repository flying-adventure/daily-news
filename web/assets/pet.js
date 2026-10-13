// 오늘의 기니피그 6마리 (이미지 생성으로 만든 픽셀 기니피그, pets/<id>-<자세>.png)
const PETS = [
  {id:'gamja', name:'감자'},
  {id:'kongtteok', name:'콩떡'},
  {id:'cookie', name:'쿠키'},
  {id:'mocha', name:'모카'},
  {id:'hotteok', name:'호떡'},
  {id:'dubu', name:'두부'},
];
const POSES = ['sleep', 'sit', 'walkA', 'walkB', 'eatA', 'eatB', 'popA', 'popB', 'groomA', 'groomB',
  'yawnA', 'yawnB', 'standA', 'standB', 'loafA', 'loafB'];
// 그림 폴더 = 이 스크립트 옆 pets/ (페이지 주소와 무관하게)
const PET_DIR = new URL('pets/', document.currentScript.src).href;
// 자세별 이미지 주소 (미리 불러와서 자세 바뀔 때 깜빡임 방지)
const petImages = pet => Object.fromEntries(POSES.map(k => { const src = `${PET_DIR}${pet.id}-${k}.png`; new Image().src = src; return [k, src]; }));
// 오늘 날짜로 고르는 기니피그 (같은 날엔 같은 아이)
function todayPet(){
  const d = new Date(), key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
  let h = 7; for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % PETS.length;
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
