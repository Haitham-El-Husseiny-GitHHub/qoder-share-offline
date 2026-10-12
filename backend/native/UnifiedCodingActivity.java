package com.qoder.share;

import android.app.*;
import android.os.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.content.*;
import android.content.res.ColorStateList;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.net.*;
import java.io.*;
import java.util.concurrent.*;

/** Native task screen for the independent on-device coding worker. */
public final class UnifiedCodingActivity extends Activity {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private LinearLayout root, feed;
    private ScrollView scroll;
    private TextView status, project, bridge;
    private long lastBridgeStart;
    private boolean bridgePermissionAsked;
    private EditText objective;
    private Button send, model, taskMode;
    private AttachmentPicker attachments;
    private Button[] tabButtons=new Button[2];
    private String[] sessionIds=new String[]{"",""};
    private int selectedTab=0, runningCount=0;
    private boolean initializing;
    private File exportFile(){return new File(getCacheDir(),"qoder-session-export.json");}
    private String sessionId(){return sessionIds[selectedTab];}
    private boolean ready, busy, stopping, refreshing, destroyed;
    private String workspace = "/data/data/com.termux/files/home/coding-workspace";
    private String profile = "BUILD", rendered = "", renderedId = "";
    private final Runnable ticker = new Runnable() {
        public void run() { refresh(); if (!destroyed) ui.postDelayed(this, 1000); }
    };

    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size) {
        TextView t = new TextView(this); t.setText(value); t.setTextSize(size);
        t.setTextColor(Color.rgb(31, 41, 35)); return t;
    }
    private GradientDrawable bg(int color, int radius) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;
    }
    private Button button(String label) {
        Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setTextSize(14);
        b.setTextColor(Color.rgb(31, 54, 39)); b.setMinHeight(dp(48));
        b.setBackgroundTintList(ColorStateList.valueOf(0xffefeff0));
        return b;
    }
    private void addWeighted(LinearLayout row, View v) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.setMargins(dp(3),0,dp(3),0); row.addView(v,p);
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        getWindow().setStatusBarColor(0xfff7f8f6); getWindow().setNavigationBarColor(0xfff7f8f6);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        workspace = getPreferences(0).getString("workspace",workspace);
        profile = "BUILD";
        root = new LinearLayout(this); root.setOrientation(1); root.setBackgroundColor(0xfff7f8f6);
        root.setPadding(dp(16),dp(12),dp(16),dp(12));
        root.setOnApplyWindowInsetsListener((v,insets)->{
            android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            int keyboard=insets.getInsets(WindowInsets.Type.ime()).bottom;
            root.setPadding(dp(16)+bars.left,dp(8)+bars.top,dp(16)+bars.right,dp(8)+Math.max(bars.bottom,keyboard));
            return insets;
        });
        LinearLayout header=new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=text("Qoder · Coding",22); title.setTypeface(null,Typeface.BOLD);
        header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        Button menu=button("⋯"); header.addView(menu,new LinearLayout.LayoutParams(dp(56),dp(48)));
        menu.setOnClickListener(v->menu(v)); root.addView(header);
        LinearLayout navigation=new LinearLayout(this);
        Button offline=button("Offline");offline.setEnabled(false);addWeighted(navigation,offline);
        Button cloud=button("Qoder");cloud.setOnClickListener(v->startActivity(new Intent().setClassName(this,"com.qoder.mobile.MainActivity")));addWeighted(navigation,cloud);
        Button openCode=button("OpenCode");openCode.setSingleLine(true);openCode.setTextSize(13);openCode.setOnClickListener(v->startActivity(new Intent().setClassName(this,"com.qoder.share.OpenCodeActivity")));addWeighted(navigation,openCode);
        root.addView(navigation);

        status=text("Connecting to local coder…",13); status.setPadding(dp(4),dp(6),0,dp(8)); root.addView(status);
        bridge=text("Termux bridge · checking Rish…",12);root.addView(bridge);
        bridge.setOnClickListener(v->{try{startActivity(new Intent().setClassName("moe.shizuku.privileged.api","moe.shizuku.manager.MainActivity"));}catch(Exception e){Toast.makeText(this,"Open Shizuku to start or authorize its service.",Toast.LENGTH_LONG).show();}});
        LinearLayout selectors=new LinearLayout(this);
        model=button("Choose offline model ▾"); model.setOnClickListener(v->modelInfo()); addWeighted(selectors,model);
        Button mode=button("BUILD");taskMode=mode;mode.setClickable(false);addWeighted(selectors,mode);root.addView(selectors);
        LinearLayout tabs=new LinearLayout(this);
        for(int i=0;i<2;i++){final int index=i;sessionIds[i]=getPreferences(0).getString("session"+i,"");tabButtons[i]=button("Session "+(i+1));tabButtons[i].setOnClickListener(v->selectTab(index));addWeighted(tabs,tabButtons[i]);}
        root.addView(tabs);
        project=text("⌂ Home",14); project.setPadding(dp(8),dp(12),dp(8),dp(12));
        project.setContentDescription("Project folder"); project.setOnClickListener(v->chooseProject()); root.addView(project); updateProject();
        scroll=new ScrollView(this); scroll.setFillViewport(true);
        feed=new LinearLayout(this); feed.setOrientation(1); scroll.addView(feed);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        attachments=new AttachmentPicker(this,new AttachmentPicker.Host(){
            public String workspace(){return workspace;}
            public String key(){return sessionId()+":"+workspace;}
            public boolean busy(){return busy;}
            public String endpoint(){return "http://127.0.0.1:8767/api/attachments";}
            public void changed(){controls();}
            public void status(String message){ui.post(()->status.setText(message));}
        },root,0xff1f3627);
        LinearLayout composer=new LinearLayout(this); composer.setGravity(Gravity.BOTTOM);
        composer.addView(attachments.button(),new LinearLayout.LayoutParams(dp(48),dp(58)));
        objective=new EditText(this); objective.setHint("Describe your coding task…"); objective.setTextSize(16);
        objective.setTextColor(0xff1f2923); objective.setHintTextColor(0xff727b74);
        objective.setMinLines(2); objective.setMaxLines(5); objective.setBackground(bg(0xffffffff,18));
        objective.setPadding(dp(14),dp(12),dp(14),dp(12));
        objective.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(8000)});
        composer.addView(objective,new LinearLayout.LayoutParams(0,-2,1));
        send=button("Run"); send.setPadding(dp(6),0,dp(6),0);send.setTextSize(13);send.setSingleLine(true);send.setOnClickListener(v->{if(busy)stop();else submit();});
        LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(dp(72),dp(58));sp.leftMargin=dp(8);composer.addView(send,sp);
        root.addView(composer);setContentView(root);root.requestApplyInsets();
        
        restoreDraft();controls();startBridge();ui.post(ticker);
    }
    private void startBridge(){
        if(destroyed||(lastBridgeStart!=0&&android.os.SystemClock.elapsedRealtime()-lastBridgeStart<30000))return;
        lastBridgeStart=android.os.SystemClock.elapsedRealtime();
        if(checkSelfPermission("com.termux.permission.RUN_COMMAND")!=android.content.pm.PackageManager.PERMISSION_GRANTED){if(!bridgePermissionAsked){bridgePermissionAsked=true;requestPermissions(new String[]{"com.termux.permission.RUN_COMMAND"},302);}if(bridge!=null)bridge.setText("Allow Qoder to run commands in Termux to reconnect automatically.");return;}
        StartupBridge.ensure(this);
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==302&&results.length>0&&results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED){lastBridgeStart=0;startBridge();}
    }
    private void rememberDraft(){
        if(sessionId().isEmpty())return;
        getPreferences(0).edit().putString(sessionId()+"draft",objective.getText().toString()).putString(sessionId()+"workspace",workspace).putString(sessionId()+"profile",profile).apply();
    }
    private void restoreDraft(){
        workspace=getPreferences(0).getString(sessionId()+"workspace","/data/data/com.termux/files/home/coding-workspace");
        profile="BUILD";if(taskMode!=null)taskMode.setText(profile);
        objective.setText(getPreferences(0).getString(sessionId()+"draft",""));updateProject();
        for(int i=0;i<2;i++){tabButtons[i].setSelected(i==selectedTab);tabButtons[i].setTypeface(null,i==selectedTab?Typeface.BOLD:Typeface.NORMAL);}
    }
    private void selectTab(int index){if(attachments!=null&&attachments.uploading())return;rememberDraft();selectedTab=index;busy=false;stopping=false;rendered="";renderedId="";feed.removeAllViews();restoreDraft();controls();refresh();}
    private void updateProject(){project.setText("⌂ "+(workspace.equals("/data/data/com.termux/files/home/coding-workspace")?"Home":workspace.replace("/data/data/com.termux/files/home/","~/")));}
    private void chooseProject(){
        if(busy||(attachments!=null&&attachments.uploading()))return;
        EditText input=new EditText(this);input.setText(workspace);input.setSingleLine(true);
        new AlertDialog.Builder(this).setTitle("Project folder").setMessage("Enter any accessible source folder or file path. Keep Home selected to automatically find the app source from your task.").setView(input)
          .setPositiveButton("Use folder",(d,w)->{workspace=input.getText().toString().trim();getPreferences(0).edit().putString("workspace",workspace).apply();updateProject();})
          .setNeutralButton("Home",(d,w)->{workspace="/data/data/com.termux/files/home/coding-workspace";getPreferences(0).edit().putString("workspace",workspace).apply();updateProject();}).setNegativeButton("Cancel",null).show();
    }
    private void menu(View anchor){
        PopupMenu p=new PopupMenu(this,anchor);p.getMenu().add("Reload local model");p.getMenu().add("Refresh status");p.getMenu().add("Default Qoder cloud models");p.getMenu().add("Save session");p.getMenu().add("Open saved session");p.getMenu().add("Clear current chat");p.getMenu().add("Delete session");p.getMenu().add("Export session");
        p.setOnMenuItemClickListener(item->{String s=item.getTitle().toString();
            if(s.startsWith("Reload")){if(runningCount==0)load();}
            else if(s.startsWith("Refresh"))refresh();
            else if(s.equals("Save session"))saveSession();
            else if(s.equals("Open saved session"))openSessions();
            else if(s.equals("Clear current chat"))manageSession("clear");
            else if(s.equals("Delete session"))new AlertDialog.Builder(this).setTitle("Delete session?").setMessage("Delete this session's messages and operation logs. Project files are retained.").setPositiveButton("Delete",(d,w)->manageSession("delete")).setNegativeButton("Cancel",null).show();
            else if(s.equals("Export session"))exportSession();
            else startActivity(new Intent().setClassName(this,"com.qoder.mobile.MainActivity"));return true;});p.show();
    }
    private void modelInfo(){
        if(runningCount>0)return;
        network.execute(()->{try{
            JSONArray items=api("/api/models",null).getJSONArray("data");
            ui.post(()->{if(destroyed)return;
                PopupMenu dropdown=new PopupMenu(this,model);
                java.util.ArrayList<Integer> order=new java.util.ArrayList<>();
                for(int i=0;i<items.length();i++)if(items.optJSONObject(i)!=null)order.add(i);
                java.util.Collections.sort(order,(left,right)->items.optJSONObject(left).optString("name").compareToIgnoreCase(items.optJSONObject(right).optString("name")));
                for(int rank=0;rank<order.size();rank++){
                    int i=order.get(rank);JSONObject m=items.optJSONObject(i);
                    String label=m.optString("name")+" · 0.0x";
                    if(!m.optBoolean("selectable"))label+=" — "+m.optString("reason");
                    MenuItem entry=dropdown.getMenu().add(0,i,rank,label);
                    entry.setEnabled(m.optBoolean("selectable"));
                    entry.setCheckable(true);entry.setChecked(model.getText().toString().startsWith(m.optString("name")));
                }
                dropdown.setOnMenuItemClickListener(entry->{
                    JSONObject m=items.optJSONObject(entry.getItemId());
                    if(m!=null && m.optBoolean("selectable") && runningCount==0)switchModel(m.optString("mode"));
                    return true;
                });
                dropdown.show();
            });
        }catch(Exception e){ui.post(()->error(e));}});
    }
    private void switchModel(String mode){
        if(runningCount>0)return;ready=false;model.setText("Loading model…");controls();
        network.execute(()->{try{api("/api/switch",new JSONObject().put("mode",mode));ui.post(()->refresh());}
            catch(Exception e){ui.post(()->{status.setText(e.getMessage());refresh();});}});
    }
    private JSONObject api(String path, JSONObject body) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8767"+path).openConnection(Proxy.NO_PROXY);
        c.setConnectTimeout(4000);c.setReadTimeout(12000);c.setRequestProperty("Origin","http://127.0.0.1:8767");
        try{
            if(body!=null){c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream o=c.getOutputStream()){o.write(body.toString().getBytes("UTF-8"));}}
            int code=c.getResponseCode();InputStream in=code<400?c.getInputStream():c.getErrorStream();
            if(in==null)throw new IOException("Backend HTTP "+code);
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream stream=in){byte[] b=new byte[8192];int n;while((n=stream.read(b))!=-1){bytes.write(b,0,n);if(bytes.size()>32*1024*1024)throw new IOException("Result too large");}}
            JSONObject j=new JSONObject(bytes.toString("UTF-8"));
            if(code>=400){Object e=j.opt("error");throw new IOException(e instanceof JSONObject?((JSONObject)e).optString("message"):String.valueOf(e));}return j;
        }finally{c.disconnect();}
    }
    private void controls(){boolean importing=attachments!=null&&attachments.uploading();send.setEnabled(!importing&&(busy?!stopping:ready));send.setText(stopping?"Stopping":busy?"Stop":"Run");send.setSelected(busy);model.setSelected(ready);model.setEnabled(runningCount==0&&!importing);objective.setEnabled(!busy);if(attachments!=null)attachments.render();}
    private void error(Exception e){if(destroyed)return;startBridge();status.setText("Local backend: "+(e.getMessage()==null?"unavailable":e.getMessage()));ready=false;controls();}
    private void refresh(){
        if(refreshing||destroyed)return;
        if(sessionId().isEmpty()){
            if(initializing)return;initializing=true;
            network.execute(()->{try{
                final int index=selectedTab;JSONObject created=api("/api/sessions",new JSONObject().put("action","new"));
                ui.post(()->{initializing=false;sessionIds[index]=created.optString("id");getPreferences(0).edit().putString("session"+index,sessionIds[index]).apply();restoreDraft();refresh();});
            }catch(Exception e){ui.post(()->{initializing=false;error(e);});}});return;
        }
        refreshing=true;final String sid=sessionId();
        network.execute(()->{try{
            JSONObject connection=api("/api/bridge",null);
            JSONObject s=api("/api/status",null),session=api("/api/session?session="+sid,null);
            ui.post(()->{refreshing=false;if(destroyed||!sid.equals(sessionId()))return;
                bridge.setText("Termux connected · "+(connection.optBoolean("rish_connected")?"Rish connected · "+connection.optString("access_level","shell")+" access":"Rish offline — tap to open Shizuku"));bridge.setTextColor(connection.optBoolean("rish_connected")?0xff3e774a:0xffa83232);
                ready=s.optBoolean("coding_ready");model.setText(s.optString("model_name","Choose model")+" · 0.0x ▾");runningCount=session.optInt("running_count");
                JSONObject job=session.optJSONObject("current");busy=job!=null && "running".equals(job.optString("status"));stopping=busy&&job.optBoolean("cancel_requested");
                status.setText(busy?"Working on your phone · 0.0x":"READY".equals(s.optString("status"))?"On-device · "+runningCount+"/2 jobs · 0.0x":s.optString("status")+" · "+s.optString("phase"));
                if(busy){JSONObject op=job.optJSONObject("current_operation");if(op!=null)status.setText(op.optString("title")+" · "+elapsed(op,job)+" · 0.0x");}
                if(stopping)status.setText("Stopping this session… · 0.0x");
                tabButtons[selectedTab].setText(session.optBoolean("saved")?session.optString("name"):"Session "+(selectedTab+1)+(busy?" ●":""));controls();renderSession(session);
            });
        }catch(Exception e){ui.post(()->{refreshing=false;error(e);});}});
    }
    private void renderSession(JSONObject session){
        String value=session.toString();if(value.equals(rendered))return;rendered=value;
        boolean follow=scroll.getScrollY()+scroll.getHeight()>=feed.getHeight()-dp(64);int position=scroll.getScrollY();feed.removeAllViews();
        JSONArray jobs=session.optJSONArray("jobs");
        if(jobs!=null)for(int i=0;i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);if(j!=null)render(j);}
        JSONObject current=session.optJSONObject("current");renderedId=current==null?"":current.optString("id");if(current!=null)render(current);
        if((jobs==null||jobs.length()==0)&&current==null)card("Coding session","Enter a task. Use the other tab for another project. Save, open, clear, delete and export sessions from ⋯.",0xffffffff);
        scroll.post(()->{if(follow)scroll.fullScroll(View.FOCUS_DOWN);else scroll.scrollTo(0,position);});
    }
    private void saveSession(){
        if(sessionId().isEmpty())return;final String sid=sessionId();EditText name=new EditText(this);name.setHint("Session name");
        new AlertDialog.Builder(this).setTitle("Save session").setView(name).setPositiveButton("Save",(d,w)->{
            network.execute(()->{try{api("/api/sessions",new JSONObject().put("action","save").put("session",sid).put("name",name.getText().toString()));ui.post(()->refresh());}catch(Exception e){ui.post(()->error(e));}});
        }).setNegativeButton("Cancel",null).show();
    }
    private void openSessions(){
        final int index=selectedTab;
        network.execute(()->{try{JSONArray all=api("/api/sessions",null).getJSONArray("data");java.util.ArrayList<JSONObject> saved=new java.util.ArrayList<>();
            for(int i=0;i<all.length();i++){JSONObject item=all.getJSONObject(i);if(item.optBoolean("saved"))saved.add(item);}
            ui.post(()->{String[] labels=new String[saved.size()];for(int i=0;i<labels.length;i++)labels[i]=saved.get(i).optString("name")+" · "+saved.get(i).optInt("job_count")+" tasks";
                new AlertDialog.Builder(this).setTitle(labels.length==0?"No saved sessions yet":"Open saved session").setItems(labels,(d,i)->{
                    if(busy){Toast.makeText(this,"Stop this tab before replacing it",Toast.LENGTH_SHORT).show();return;}
                    String id=saved.get(i).optString("id");if(id.equals(sessionIds[1-index])){selectTab(1-index);return;}
                    rememberDraft();sessionIds[index]=id;getPreferences(0).edit().putString("session"+index,id).apply();getPreferences(0).edit().putString(id+"workspace",saved.get(i).optString("workspace","/data/data/com.termux/files/home/coding-workspace")).putString(id+"profile","BUILD").apply();selectedTab=index;busy=false;stopping=false;rendered="";restoreDraft();refresh();
                }).setNegativeButton("Cancel",null).show();});
        }catch(Exception e){ui.post(()->error(e));}});
    }
    private void manageSession(String action){
        if(busy){Toast.makeText(this,"Stop this session first",Toast.LENGTH_SHORT).show();return;}
        final String sid=sessionId(),selectedWorkspace=workspace,selectedProfile=profile;final int index=selectedTab;
        network.execute(()->{try{JSONObject r=api("/api/sessions",new JSONObject().put("action",action).put("session",sid));
            if(action.equals("delete"))r=api("/api/sessions",new JSONObject().put("action","new"));final String id=r.optString("id",sid);
            ui.post(()->{exportFile().delete();sessionIds[index]=id;getPreferences(0).edit().putString("session"+index,id).putString(id+"workspace",selectedWorkspace).putString(id+"profile",selectedProfile).remove(sid+"draft").apply();if(index==selectedTab){busy=false;stopping=false;rendered="";renderedId="";restoreDraft();refresh();}});
        }catch(Exception e){ui.post(()->error(e));}});
    }
    private void exportSession(){
        final String sid=sessionId();network.execute(()->{try{String data=api("/api/session/export?session="+sid,null).toString(2);try(FileOutputStream out=new FileOutputStream(exportFile())){out.write(data.getBytes("UTF-8"));}ui.post(()->{
            Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/json");intent.putExtra(Intent.EXTRA_TITLE,"Qoder-session-"+sid.substring(0,8)+".json");startActivityForResult(intent,301);
        });}catch(Exception e){ui.post(()->error(e));}});
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(attachments!=null&&attachments.result(request,result,data))return;
        if(request==301&&result!=RESULT_OK)exportFile().delete();
        if(request==301&&result==RESULT_OK&&data!=null&&data.getData()!=null){final android.net.Uri uri=data.getData();
            network.execute(()->{try(OutputStream out=getContentResolver().openOutputStream(uri);InputStream in=new FileInputStream(exportFile())){byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);ui.post(()->Toast.makeText(this,"Session exported",Toast.LENGTH_SHORT).show());}catch(Exception e){ui.post(()->error(e));}finally{exportFile().delete();}});
        }
    }
    private void card(String label,String content,int color){
        LinearLayout box=new LinearLayout(this);box.setOrientation(1);box.setPadding(dp(14),dp(12),dp(14),dp(12));box.setBackground(bg(color,16));
        TextView heading=text(label,14);heading.setTypeface(null,Typeface.BOLD);box.addView(heading);
        TextView body=text(content,16);body.setTextIsSelectable(true);body.setPadding(0,dp(6),0,0);box.addView(body);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);feed.addView(box,p);
    }
    private String elapsed(JSONObject op,JSONObject job){
        double end=op.optDouble("finished_at",job.optDouble("observed_at",System.currentTimeMillis()/1000.0));
        long seconds=Math.max(0,(long)(end-op.optDouble("started_at",end)));
        return seconds>=60?(seconds/60)+"m "+(seconds%60)+"s":seconds+"s";
    }
    private void operation(JSONObject op,JSONObject job){
        String state=op.optString("status"),title=op.optString("title"),detail=op.optString("detail");
        String mark="running".equals(state)?"● ":"failed".equals(state)?"✕ ":"stopped".equals(state)?"■ ":"✓ ";
        String time=new java.text.SimpleDateFormat("HH:mm:ss",java.util.Locale.getDefault()).format(new java.util.Date((long)(op.optDouble("started_at")*1000)));
        String content=time+" · "+elapsed(op,job);
        if(!detail.isEmpty())content+="\n"+detail;
        if("generating".equals(op.optString("kind")))content+="\n"+op.optInt("generated_chars")+" characters received";
        if(op.has("exit_code"))content+="\nExit code: "+op.optInt("exit_code");
        String output=op.optString("output");if(!output.isEmpty())content+="\n\n"+output;
        card(mark+title,content,"failed".equals(state)?0xffffe9e4:"running".equals(state)?0xffd3e7ce:0xffedf0ed);
    }
    private void render(JSONObject job){
        String value=job.toString();
        
        if(!job.has("id")){card("Coding workspace","Describe a change, fix a bug, or ask for a review. Live file operations and command output appear here.",0xffffffff);return;}
        card("You · "+job.optString("profile"),job.optString("objective"),0xffe9ece8);
        JSONArray activity=job.optJSONArray("activity");
        if(activity!=null && activity.length()>0){
            for(int i=Math.max(0,activity.length()-60);i<activity.length();i++){JSONObject op=activity.optJSONObject(i);if(op!=null)operation(op,job);}
        }else{
            JSONArray evidence=job.optJSONArray("evidence");
            if(evidence!=null)for(int i=0;i<evidence.length();i++){
                JSONObject step=evidence.optJSONObject(i);if(step==null)continue;
                Object result=step.opt("result");boolean failed=result instanceof JSONObject && (((JSONObject)result).has("error")||((JSONObject)result).optInt("exit_code",0)!=0);
                card((failed?"✕ ":"✓ ")+step.optString("tool"),step.optString("arguments")+"\n"+String.valueOf(result),failed?0xffffe9e4:0xffedf0ed);
            }
        }
        String state=job.optString("status"),result=job.optString("result");
        if("running".equals(state)){
            if(activity==null||activity.length()==0)card("● Starting local task","Waiting for the coding worker…",0xffd3e7ce);
        }else if("stopped".equals(state))card("Coder · Stopped",result,0xffedf0ed);
        else if("completed".equals(state))card("Coder · Finished",result.isEmpty()?"Task completed. Inspect the file and command evidence.":result,0xffe0eedc);
        else card("Coder · "+state,job.optString("error","Task interrupted. Inspect the evidence before retrying."),0xffffe9e4);
    }
    private void stop(){
        if(!busy||stopping||renderedId.isEmpty())return;stopping=true;controls();status.setText("Stopping current action…");
        final String id=renderedId,sid=sessionId();
        network.execute(()->{try{api("/api/session/stop",new JSONObject().put("id",id).put("session",sid));ui.post(()->refresh());}
            catch(Exception e){ui.post(()->{stopping=false;status.setText(e.getMessage());controls();refresh();});}});
    }
    private void submit(){
        String prompt=objective.getText().toString().trim();if(prompt.isEmpty()||busy||!ready)return;
        if(attachments.uploading())return;
        final String attachmentKey=sessionId()+":"+workspace;
        final String task=prompt+attachments.prompt();
        send.setBackgroundTintList(ColorStateList.valueOf(0xffefeff0));busy=true;controls();status.setText("Starting local task…");
        final String path=workspace,taskProfile=profile,sid=sessionId();rememberDraft();
        network.execute(()->{try{JSONObject body=new JSONObject();body.put("workspace",path);body.put("profile",taskProfile);body.put("objective",task);body.put("session",sid);api("/api/session/run",body);
            ui.post(()->{if(destroyed)return;attachments.clear(attachmentKey);if(sid.equals(sessionId())){objective.setText("");rememberDraft();send.setBackgroundTintList(ColorStateList.valueOf(0xffd3e7ce));}refresh();});
        }catch(Exception e){ui.post(()->{if(sid.equals(sessionId())){busy=false;status.setText(e.getMessage());send.setBackgroundTintList(ColorStateList.valueOf(0xffffead4));controls();}refresh();});}});
    }
    private void load(){if(runningCount>0)return;ready=false;controls();status.setText("Loading coding model…");network.execute(()->{try{api("/api/switch",new JSONObject().put("mode","coding"));ui.post(()->refresh());}catch(Exception e){ui.post(()->error(e));}});}
    @Override protected void onSaveInstanceState(Bundle out){rememberDraft();out.putString("draft",objective.getText().toString());super.onSaveInstanceState(out);}
    @Override protected void onDestroy(){destroyed=true;ui.removeCallbacks(ticker);network.shutdownNow();if(attachments!=null)attachments.close();super.onDestroy();}
}
