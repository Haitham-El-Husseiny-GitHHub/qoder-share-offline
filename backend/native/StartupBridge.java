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
 private static void attachCloudNavigation(Activity activity){
  if(!activity.getClass().getName().equals("com.qoder.mobile.MainActivity"))return;
  android.view.View bar=activity.findViewById(0x51a71003);
  if(!(bar instanceof android.widget.LinearLayout))return;
  android.widget.LinearLayout row=(android.widget.LinearLayout)bar;
  android.view.View offline=activity.findViewById(0x51a71002);
  if(offline instanceof android.widget.Button)((android.widget.Button)offline).setText("Offline");
  android.view.View restart=activity.findViewById(0x51a71001);
  if(restart instanceof android.widget.Button)LocalhostButton.attach(activity,(android.widget.Button)restart);
  if(activity.findViewById(0x51a71004)!=null){styleNavigation(row);QoderEnhancements.attach(activity);return;}
  android.widget.Button button=new android.widget.Button(activity);
  button.setId(0x51a71004);button.setText("OpenCode");button.setAllCaps(false);
  button.setTextSize(13);button.setMinWidth(0);button.setMinimumWidth(0);
  button.setTextColor(0xff2a372f);button.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xffefeff0));
  android.widget.LinearLayout.LayoutParams params=new android.widget.LinearLayout.LayoutParams(0,-1,1);
  params.leftMargin=4;params.rightMargin=4;
  button.setOnClickListener(v->activity.startActivity(new Intent().setClassName(activity,"com.qoder.share.OpenCodeActivity")));
  row.addView(button,params);
  styleNavigation(row);
  QoderEnhancements.attach(activity);
 }
 private static void styleNavigation(android.widget.LinearLayout row){
  int padding=(int)(6*row.getResources().getDisplayMetrics().density);
  for(int i=0;i<row.getChildCount();i++){
   android.view.View child=row.getChildAt(i);if(!(child instanceof android.widget.Button))continue;
   android.widget.Button b=(android.widget.Button)child;
   b.setAllCaps(false);b.setSingleLine(true);b.setHorizontallyScrolling(false);b.setMaxLines(1);
   b.setPadding(padding,0,padding,0);b.setMinWidth(0);b.setMinimumWidth(0);
   b.setAutoSizeTextTypeUniformWithConfiguration(10,13,1,android.util.TypedValue.COMPLEX_UNIT_SP);
  }
 }
 public static synchronized void install(Application app){
  if(installed)return;installed=true;
  app.registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks(){
   public void onActivityCreated(Activity a,Bundle state){}
   public void onActivityStarted(Activity a){}
   public void onActivityResumed(Activity a){visible=new WeakReference<>(a);main.postDelayed(()->{ensure(a);attachCloudNavigation(a);},350);main.postDelayed(()->attachCloudNavigation(a),1000);}
   public void onActivityPaused(Activity a){if(visible.get()==a)visible.clear();}
   public void onActivityStopped(Activity a){}
   public void onActivitySaveInstanceState(Activity a,Bundle state){}
   public void onActivityDestroyed(Activity a){if(visible.get()==a)visible.clear();}
  });
  main.post(new Runnable(){public void run(){Activity a=visible.get();if(a!=null){ensure(a);attachCloudNavigation(a);}main.postDelayed(this,15000);}});
 }
}
