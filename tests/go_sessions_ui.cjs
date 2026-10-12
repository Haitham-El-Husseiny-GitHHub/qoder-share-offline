const {chromium}=require('playwright');const fs=require('fs');const assert=require('assert');const path=require('path');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.QODER_TEST_CHROME||undefined,headless:true,args:['--no-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:393,height:852}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const model={id:'deepseek-v4-pro',name:'DeepSeek V4 Pro',developer:'DeepSeek',available:true,pricing_schedule:'deepseek',pricing:{peak:{input:1.32,output:3.96},offpeak:{input:.66,output:1.98}}};
 await page.route('http://127.0.0.1:8767/**',async route=>{
 const url=new URL(route.request().url());let data={};if(route.request().method()==='POST'&&JSON.parse(route.request().postData()||'{}').action==='run'){const body=JSON.parse(route.request().postData());assert.equal(body.session,'s1');assert.equal(body.directory,'/project/one');assert.equal(body.model,'opencode-go/claude-a');}
 if(url.pathname==='/opencode')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../backend/opencode.html'),'utf8')});
 if(url.pathname==='/opencode.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(__dirname,'../backend/opencode.js'),'utf8')});
 if(url.pathname==='/api/bridge')data={termux:true,rish_connected:false,access_level:'offline'};
 else if(url.pathname==='/api/account/go')data={available:false,connected:false,label:'Go allowance: connect account',detail:'Account console required'};
 else if(route.request().method()==='POST')data={accepted:true,session:'s1',directory:'/project/one'};
 else switch(url.searchParams.get('path')){
 case '/global/health':data={healthy:true,version:'test'};break;
 case '/provider':assert.equal(url.searchParams.get('provider'),'opencode-go');data={providers:[{models:[model,{id:'fixed',name:'Fixed Model',developer:'OpenCode',cost:{input:.3,output:1.2},available:true},{id:'deepseek-alt',name:'DeepSeek V4 Pro',developer:'DeepSeek',cost:{input:2,output:5},available:true},{id:'claude-z',name:'Zulu Claude',developer:'Anthropic',cost:{input:3,output:9},available:true},{id:'claude-a',name:'Alpha Claude',developer:'Anthropic',cost:{input:1,output:2},available:true}]}],catalog:{}};break;
 case '/session':data=[{id:'s1',title:'First project',directory:'/project/one'},{id:'s2',title:'Second project',directory:'/project/two'}];break;
 case '/session/status':data={};break;
 default:data=[{info:{role:'assistant'},parts:[{type:'text',text:'Ready to code'}]}];
 }
 return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto('http://127.0.0.1:8767/opencode');await page.getByRole('button',{name:'First project'}).click();
 assert.equal(await page.locator('#allowance').textContent(),'Go allowance: connect account');await page.locator('#allowance').click();assert.equal(await page.locator('#credentials').evaluate(e=>e.open),true);await page.locator('#closeKey').click();
 await page.locator('#objective').fill('Draft for project one');await page.locator('#back').click();await page.getByRole('button',{name:'Second project'}).click();assert.equal(await page.locator('#objective').inputValue(),'');
 await page.locator('#objective').fill('Draft for project two');await page.locator('#back').click();await page.getByRole('button',{name:'First project'}).click();assert.equal(await page.locator('#objective').inputValue(),'Draft for project one');
 await page.locator('#provider').click();assert.deepEqual(await page.locator('#providerRows .providerrow').allTextContents(),['Anthropic2 models','DeepSeek2 models','OpenCode1 models']);await page.locator('#providerRows .providerrow').filter({hasText:'DeepSeek'}).click();assert.equal(await page.locator('.modelrow').count(),2);await page.locator('.modelrow').filter({hasText:'deepseek-v4-pro'}).click();
 await page.locator('#model').click();assert.equal(await page.locator('.modelrow').count(),2);assert.equal(await page.locator('#directory,#filter,#providerList').count(),0);
 const states=await page.evaluate(()=>[price(models.find(m=>m.id==='deepseek-v4-pro'),new Date('2026-10-12T00:59:59Z')).state,price(models.find(m=>m.id==='deepseek-v4-pro'),new Date('2026-10-12T01:00:00Z')).state,price(models.find(m=>m.id==='deepseek-v4-pro'),new Date('2026-10-12T04:00:00Z')).state,price(models.find(m=>m.id==='deepseek-v4-pro'),new Date('2026-10-10T02:00:00Z')).state,price(models.find(m=>m.id==='fixed'),new Date('2026-10-12T02:00:00Z')).state]);assert.deepEqual(states,['offpeak','peak','offpeak','offpeak','standard']);
 assert.equal(await page.locator('#rish').getAttribute('class'),'bad');assert.equal(await page.locator('#termux').getAttribute('class'),'good');
 await page.locator('#closeModels').click();await page.locator('#provider').click();await page.locator('#providerRows .providerrow').filter({hasText:'Anthropic'}).click();assert.match((await page.locator('.modelrow').allTextContents())[0],/^Alpha Claude/);assert.equal(await page.locator('#send').isDisabled(),true);await page.locator('.modelrow').filter({hasText:'Alpha Claude'}).click();await page.locator('#send').click();
 await page.locator('#connection').click();await page.locator('#chooseLocalhost').click();assert.equal(await page.locator('#localhost').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#connectionStatus').textContent(),'CLI · localhost connected');
 await page.locator('#menu').click();assert.equal(await page.locator('#closeOptions').textContent(),'×');assert.equal(await page.locator('#diff').textContent(),'Changed files');await page.locator('#closeOptions').click();await page.locator('#back').click();await page.locator('#menu').click();assert.equal(await page.locator('#diff').isVisible(),false);await page.locator('#closeOptions').click();await page.getByRole('button',{name:'First project'}).click();assert.match(await page.locator('#provider').textContent(),/Anthropic/);assert.match(await page.locator('#model').textContent(),/Alpha Claude/);
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/tmp/qoder-go-chat.png',fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
 console.log('PASS: sessions, isolated drafts, Go provider, pricing boundaries, honest status and mobile width');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
