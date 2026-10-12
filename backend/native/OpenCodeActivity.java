package com.qoder.share;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.graphics.Color;
import android.view.WindowInsets;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.Button;
/** OpenCode Go session list and chat using the authenticated local adapter. */
public final class OpenCodeActivity extends Activity {
 private WebView web;
 private android.webkit.ValueCallback<android.net.Uri[]> files;
 private static final int PICK_FILES=411;
 public void onCreate(Bundle state){
  super.onCreate(state);StartupBridge.ensure(this);
  LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(0xfff7f8f6);
  root.setOnApplyWindowInsetsListener((v,insets)->{
   android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
   root.setPadding(bars.left,bars.top,bars.right,Math.max(bars.bottom,insets.getInsets(WindowInsets.Type.ime()).bottom));return insets;
  });
  LinearLayout tabs=new LinearLayout(this);
  String[] labels={"Offline","Qoder","OpenCode"};
  String[] activities={"com.qoder.share.UnifiedCodingActivity","com.qoder.share.CloudCatalogActivity",""};
  for(int i=0;i<3;i++){final String target=activities[i];Button b=new Button(this);b.setText(labels[i]);b.setAllCaps(false);b.setSingleLine(true);b.setTextSize(13);b.setMinWidth(0);b.setMinimumWidth(0);b.setTextColor(Color.rgb(31,54,39));b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xffefeff0));if(i==2)b.setTypeface(null,android.graphics.Typeface.BOLD);tabs.addView(b,new LinearLayout.LayoutParams(0,-2,1));b.setOnClickListener(v->{if(!target.isEmpty()){startActivity(new Intent().setClassName(this,target));finish();}});}
  root.addView(tabs);
  web=new WebView(this);web.setBackgroundColor(0xfff7f8f6);
  web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);
  web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(true);
  web.setWebChromeClient(new android.webkit.WebChromeClient(){
   public boolean onShowFileChooser(WebView view,android.webkit.ValueCallback<android.net.Uri[]> callback,FileChooserParams params){
    if(files!=null)files.onReceiveValue(null);files=callback;
    Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
    pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
    try{startActivityForResult(pick,PICK_FILES);}catch(Exception e){files.onReceiveValue(null);files=null;}return true;
   }
  });
  web.setWebViewClient(new WebViewClient(){
   public boolean shouldOverrideUrlLoading(WebView view,android.webkit.WebResourceRequest request){
    android.net.Uri uri=request.getUrl();
    if("http".equals(uri.getScheme())&&"127.0.0.1".equals(uri.getHost())&&uri.getPort()==8767)return false;
    if("https".equals(uri.getScheme())&&"opencode.ai".equals(uri.getHost()))startActivity(new Intent(Intent.ACTION_VIEW,uri));
    return true;
   }
  });
  root.addView(web,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
  web.loadUrl("http://127.0.0.1:8767/opencode");
 }
 protected void onActivityResult(int request,int result,Intent data){
  if(request!=PICK_FILES){super.onActivityResult(request,result,data);return;}
  if(files==null)return;
  java.util.ArrayList<android.net.Uri> selected=new java.util.ArrayList<>();
  if(result==RESULT_OK&&data!=null){if(data.getClipData()!=null)for(int i=0;i<data.getClipData().getItemCount();i++)selected.add(data.getClipData().getItemAt(i).getUri());else if(data.getData()!=null)selected.add(data.getData());}
  files.onReceiveValue(selected.isEmpty()?null:selected.toArray(new android.net.Uri[0]));files=null;
 }
 public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
 protected void onDestroy(){if(files!=null){files.onReceiveValue(null);files=null;}if(web!=null)web.destroy();super.onDestroy();}
}
