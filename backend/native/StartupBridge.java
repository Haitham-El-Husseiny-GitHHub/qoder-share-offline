package com.qoder.share;
import android.app.Application;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import java.lang.ref.WeakReference;
/** One automatic Termux bridge shared by every app screen. */
public final class StartupBridge {
 private static boolean installed;
 private static long lastStart;
 private static WeakReference<Activity> visible=new WeakReference<>(null);
 private static final Handler main=new Handler(Looper.getMainLooper());
 public static synchronized void ensure(Context context){
  long now=SystemClock.elapsedRealtime();
  if(lastStart>0&&now-lastStart<15000)return;
  if(context.checkSelfPermission("com.termux.permission.RUN_COMMAND")!=PackageManager.PERMISSION_GRANTED)return;
  try{
   Intent intent=new Intent("com.termux.RUN_COMMAND").setClassName("com.termux","com.termux.app.RunCommandService");
   intent.putExtra("com.termux.RUN_COMMAND_PATH","/data/data/com.termux/files/usr/bin/sh");
   intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS",new String[]{"/data/data/com.termux/files/home/qoder-selfhost/bridge-start.sh"});
   intent.putExtra("com.termux.RUN_COMMAND_WORKDIR","/data/data/com.termux/files/home");
   intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND",true);
   context.startService(intent);lastStart=now;
  }catch(Exception ignored){lastStart=0;}
 }
 public static synchronized void install(Application app){
  if(installed)return;installed=true;
  app.registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks(){
   public void onActivityCreated(Activity a,Bundle state){}
   public void onActivityStarted(Activity a){}
   public void onActivityResumed(Activity a){visible=new WeakReference<>(a);main.postDelayed(()->ensure(a),350);}
   public void onActivityPaused(Activity a){if(visible.get()==a)visible.clear();}
   public void onActivityStopped(Activity a){}
   public void onActivitySaveInstanceState(Activity a,Bundle state){}
   public void onActivityDestroyed(Activity a){if(visible.get()==a)visible.clear();}
  });
  main.post(new Runnable(){public void run(){Activity a=visible.get();if(a!=null)ensure(a);main.postDelayed(this,15000);}});
 }
}
