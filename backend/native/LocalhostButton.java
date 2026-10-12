package com.qoder.share;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.widget.Button;
import android.widget.Toast;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.ByteArrayOutputStream;

/** Green only after the replacement localhost daemon confirms its connection. */
public final class LocalhostButton {
 private static final Handler main=new Handler(Looper.getMainLooper());
 private static boolean pending;
 public static void attach(Activity a,Button b){b.setOnClickListener(v->restart(a,b));}
 private static void finish(Activity a,Button b,boolean success,String message){pending=false;main.post(()->{if(a.isDestroyed())return;b.setEnabled(true);b.setText("Restart localhost");b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(success?0xffd3e7ce:0xffffead4));Toast.makeText(a,message,Toast.LENGTH_LONG).show();});}
 private static JSONObject status()throws Exception {
  HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8767/api/localhost").openConnection();c.setConnectTimeout(2000);c.setReadTimeout(2000);
  try(java.io.InputStream in=c.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[2048];int n;while((n=in.read(buffer))>0)out.write(buffer,0,n);return new JSONObject(out.toString("UTF-8"));}finally{c.disconnect();}
 }
 private static void restart(Activity a,Button b){
  if(pending)return;
  if(a.checkSelfPermission("com.termux.permission.RUN_COMMAND")!=PackageManager.PERMISSION_GRANTED){a.requestPermissions(new String[]{"com.termux.permission.RUN_COMMAND"},0x710);Toast.makeText(a,"Allow Termux commands, then tap Restart localhost.",Toast.LENGTH_LONG).show();return;}
  final long requested=System.currentTimeMillis();
  try{
   Intent i=new Intent("com.termux.RUN_COMMAND").setClassName("com.termux","com.termux.app.RunCommandService");
   i.putExtra("com.termux.RUN_COMMAND_PATH","/data/data/com.termux/files/usr/bin/python3");
   i.putExtra("com.termux.RUN_COMMAND_ARGUMENTS",new String[]{"/data/data/com.termux/files/home/qoder-selfhost/restart_localhost.py"});
   i.putExtra("com.termux.RUN_COMMAND_WORKDIR","/data/data/com.termux/files/home");i.putExtra("com.termux.RUN_COMMAND_BACKGROUND",true);
   if(a.startService(i)==null)throw new Exception("Termux unavailable");
   pending=true;b.setEnabled(false);b.setText("Restarting…");b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xffefeff0));
   new Thread(()->{for(int attempt=0;attempt<55;attempt++){try{Thread.sleep(1000);JSONObject s=status();if(s.optDouble("requested_at")*1000<requested-2000)continue;
    if(s.optBoolean("connected")){finish(a,b,true,"Localhost reconnected.");return;}if("failed".equals(s.optString("phase"))){finish(a,b,false,s.optString("error","Localhost restart failed."));return;}
   }catch(Exception ignored){}}finish(a,b,false,"Localhost reconnection could not be confirmed. Check Termux.");},"localhost-restart-status").start();
  }catch(Exception e){finish(a,b,false,"Could not start Termux. Open Termux and retry.");}
 }
}
