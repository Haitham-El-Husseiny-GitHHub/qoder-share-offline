package com.qoder.share;
import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Typeface;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.ByteArrayOutputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.*;
import org.json.*;

/** Keep the original Qoder Sessions/chat UI and add its account/catalogue data. */
public final class QoderEnhancements {
 private static final int ID=0x51a71005;
 private static final Handler main=new Handler(Looper.getMainLooper());
 private static volatile JSONObject account;
 private static volatile JSONObject bridge;
 private static volatile JSONArray published;
 private static volatile boolean updating;
 private static volatile long checked;
 private static final LinkedHashMap<String,Double> fallback=new LinkedHashMap<>();
 static {String[] names={"Auto","Ultimate","Performance","Efficient","Qwen3.8-Max","Qwen3.8-Flash","Qwen3.7-Max","Qwen3.7-Plus","DeepSeek-V4-Pro","DeepSeek-V4-Flash","GLM-5.3","GLM-5.3-Flash","GLM-5.2","Kimi-K3","Kimi-K2.8-Preview","Kimi-K2.7-Code","MiniMax-M3"};double[] prices={1,1.6,1.1,.3,.5,.1,.5,.1,.8,.3,.6,.1,.6,.8,.8,.3,.2};for(int i=0;i<names.length;i++)fallback.put(names[i],prices[i]);}
 private static JSONObject get(String path)throws Exception {
  HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8767"+path).openConnection();
  c.setConnectTimeout(3000);c.setReadTimeout(25000);
  try(java.io.InputStream in=c.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;while((n=in.read(b))>0){out.write(b,0,n);if(out.size()>1024*1024)throw new Exception("Oversize account response");}return new JSONObject(out.toString("UTF-8"));}finally{c.disconnect();}
 }
 public static void attach(Activity a){
  View navigation=a.findViewById(0x51a71003);if(navigation==null)return;
  TextView strip=(TextView)a.findViewById(ID);
  if(strip==null){
   strip=new TextView(a);strip.setId(ID);strip.setTextSize(11);strip.setSingleLine(true);strip.setBackgroundColor(0xfff7f8f6);strip.setPadding(8,0,8,0);
   float d=a.getResources().getDisplayMetrics().density;int height=(int)(32*d);
   FrameLayout.LayoutParams nav=(FrameLayout.LayoutParams)navigation.getLayoutParams();
   FrameLayout.LayoutParams p=new FrameLayout.LayoutParams(-1,height);p.topMargin=nav.topMargin+nav.height;p.leftMargin=nav.leftMargin;p.rightMargin=nav.rightMargin;
   ViewGroup content=(ViewGroup)a.findViewById(android.R.id.content);
   for(int i=0;i<content.getChildCount();i++){View v=content.getChildAt(i);ViewGroup.LayoutParams lp=v.getLayoutParams();if(lp instanceof FrameLayout.LayoutParams){FrameLayout.LayoutParams f=(FrameLayout.LayoutParams)lp;f.topMargin+=height;v.setLayoutParams(f);}}
   ((ViewGroup)a.getWindow().getDecorView()).addView(strip,p);
   strip.setContentDescription("Qoder credits, API key and attachments");strip.setOnClickListener(v->showAccount(a));
  }
  render(strip);
  if(updating||System.currentTimeMillis()-checked<15000)return;
  updating=true;final TextView target=strip;
  new Thread(()->{try{bridge=get("/api/bridge");}catch(Exception e){bridge=null;}try{account=get("/api/account/qoder");}catch(Exception e){account=null;}try{published=get("/api/qoder-cloud/models").getJSONArray("models");}catch(Exception ignored){}checked=System.currentTimeMillis();updating=false;main.post(()->{if(!a.isDestroyed())render(target);});},"qoder-account-status").start();
 }
 private static void render(TextView strip){
  boolean termux=bridge!=null&&bridge.optBoolean("termux"),rish=bridge!=null&&bridge.optBoolean("rish_connected");
  String balance=account!=null&&account.optBoolean("available")?format(account.optDouble("remaining",0))+" Credits"+(account.optBoolean("stale")?" · stale":""):"Credits · unavailable";
  android.text.SpannableString text=new android.text.SpannableString((termux?"Termux ✓":"Termux ×")+" · "+(rish?"Rish ✓ · Shell ✓":"Rish × · Shell ×")+"   |   "+balance);
  int end=text.toString().indexOf("   |");
  text.setSpan(new android.text.style.ForegroundColorSpan(termux&&rish?0xff347647:0xffa83232),0,end,0);
  text.setSpan(new android.text.style.ForegroundColorSpan(0xff303a34),end,text.length(),0);strip.setText(text);
 }
 private static void showAccount(Activity a){
  JSONObject data=account;StringBuilder text=new StringBuilder();
  if(data!=null&&data.optBoolean("available")){JSONArray parts=data.optJSONArray("parts");if(parts!=null)for(int i=0;i<parts.length();i++){JSONObject p=parts.optJSONObject(i);text.append(p.optString("label")).append(": ").append(format(p.optDouble("remaining"))).append(" Credits remaining\n");}
   text.append("\nUpdated ").append(new java.text.SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(new Date((long)(data.optDouble("checked_at")*1000))));
  }else text.append("Account credit data could not be refreshed.");
  new AlertDialog.Builder(a).setTitle("Qoder credits").setMessage(text).setPositiveButton("Refresh",(d,w)->{checked=0;attach(a);}).setNegativeButton("API key",(d,w)->QoderCredentials.show(a)).setNeutralButton("Attach files",(d,w)->QoderAttachments.show(a)).show();
 }
 private static String format(double n){return java.math.BigDecimal.valueOf(n).stripTrailingZeros().toPlainString();}
 private static Field field(Object o,String name)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);return f;}
 private static String name(String value){return value==null?"":value.split(" · ")[0].replace("🔴 ","").replace("🟢 ","");}
 private static String key(String value){return name(value).toLowerCase(Locale.ROOT).replace("deepseek-flash","deepseek-v4-flash");}
 /** Decorate a copy of each entry; IDs, permissions and the server's price remain intact. */
 public static ArrayList augment(List input){
  ArrayList result=new ArrayList();Set<String> seen=new HashSet<>();Class<?> type=null;
  if(input!=null)for(Object model:input)try{
   if(!model.getClass().getName().equals("x7.Y")){result.add(model);continue;}type=model.getClass();String id=(String)field(model,"a").get(model);String label=name((String)field(model,"b").get(model));seen.add(key(id));seen.add(key(label));
   result.add(copy(type,model,id,label,field(model,"d").getDouble(model),false));
  }catch(Exception e){result.add(model);}
  try{
   if(type==null)type=Class.forName("x7.Y");LinkedHashMap<String,Double> models=new LinkedHashMap<>(fallback);
   JSONArray rows=published;if(rows!=null)for(int i=0;i<rows.length();i++){JSONObject row=rows.optJSONObject(i);String n=row.optString("name");if(!n.isEmpty())models.put(n,row.has("cli_multiplier")?row.optDouble("cli_multiplier"):fallback.get(n));}
   for(Map.Entry<String,Double> entry:models.entrySet())if(!seen.contains(key(entry.getKey()))){String id=entry.getKey();if(Arrays.asList("Auto","Ultimate","Performance","Efficient").contains(id))id=id.toLowerCase(Locale.ROOT);result.add(copy(type,null,id,entry.getKey(),entry.getValue()==null?Double.NaN:entry.getValue(),true));seen.add(key(id));}
  }catch(Exception ignored){}
  Collections.sort(result,(left,right)->{try{int order=name((String)field(left,"b").get(left)).compareToIgnoreCase(name((String)field(right,"b").get(right)));return order!=0?order:((String)field(left,"a").get(left)).compareToIgnoreCase((String)field(right,"a").get(right));}catch(Exception e){return 0;}});
  return result;
 }
 private static Object copy(Class<?> type,Object old,String id,String label,double factor,boolean estimate)throws Exception {
  String state="",prefix="";double shown=factor;
  Calendar utc=Calendar.getInstance(TimeZone.getTimeZone("UTC"));int hour=utc.get(Calendar.HOUR_OF_DAY),day=utc.get(Calendar.DAY_OF_WEEK);
  String k=key(id);boolean qwen=k.equals("qwen3.8-max")||k.equals("qwen3.7-plus"),deepseek=k.startsWith("deepseek-v4");
  if(qwen||deepseek){boolean peak=qwen?hour<14:(day>=Calendar.MONDAY&&day<=Calendar.FRIDAY&&((hour>=1&&hour<4)||(hour>=6&&hour<10)));prefix=peak?"🔴 ":"🟢 ";state=peak?" · Peak":" · Off-Peak";
   if(estimate&&!peak)shown=factor*(qwen?.4:.5);
  }
  String price=Double.isNaN(shown)?"price unpublished":(estimate?"~":"")+format(shown)+"×";
  String display=prefix+label+" · "+price+state;
  String desc=old==null?"Published Qoder model. Account access is checked by Qoder when selected.":(String)field(old,"c").get(old);
  if(old==null)desc+=(estimate?" Published CLI reference rate.":"");
  for(Constructor<?> c:type.getConstructors())if(c.getParameterTypes().length==12)return c.newInstance(id,display,desc,Double.isNaN(factor)?0:factor,old==null?false:field(old,"e").getBoolean(old),old==null?false:field(old,"f").getBoolean(old),old==null?"qoder":field(old,"g").get(old),old==null?null:field(old,"h").get(old),old==null?Collections.emptyList():field(old,"i").get(old),old==null?null:field(old,"j").get(old),old==null?null:field(old,"k").get(old),old==null?null:field(old,"l").get(old));
  throw new Exception("Qoder model schema changed");
 }
}
