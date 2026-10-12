package com.qoder.share;
import android.app.*;
import android.widget.*;
import org.json.*;
import java.net.*;
import java.io.*;
public final class QoderCredentials {
 private static JSONObject request(JSONObject body)throws Exception {
  HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8767/api/account/qoder/key").openConnection();c.setConnectTimeout(3000);c.setReadTimeout(10000);
  try{if(body!=null){c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Origin","http://127.0.0.1:8767");c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(body.toString().getBytes("UTF-8"));}}
   if(c.getResponseCode()>=400)throw new IOException("Could not save the Qoder key.");
   try(InputStream in=c.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[1024];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>8192)throw new IOException("Invalid response.");}return new JSONObject(out.toString("UTF-8"));}
  }finally{c.disconnect();}
 }
 public static void show(Activity a){
  LinearLayout box=new LinearLayout(a);box.setOrientation(1);box.setPadding(30,16,30,16);
  LinearLayout header=new LinearLayout(a);TextView title=new TextView(a);title.setText("Qoder API key");title.setTextSize(22);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));Button close=new Button(a);close.setText("×");close.setContentDescription("Close Qoder key card");header.addView(close);box.addView(header);
  TextView description=new TextView(a);description.setText("Personal access token · saved until you replace or remove it.");box.addView(description);
  EditText key=new EditText(a);key.setHint("Qoder personal access token");key.setSingleLine(true);key.setInputType(129);box.addView(key);
  TextView status=new TextView(a);box.addView(status);
  Button save=new Button(a);save.setText("Connect");box.addView(save);Button remove=new Button(a);remove.setText("Remove saved key");box.addView(remove);
  AlertDialog dialog=new AlertDialog.Builder(a).setView(box).create();close.setOnClickListener(v->dialog.dismiss());dialog.setOnDismissListener(d->key.setText(""));dialog.show();
  new Thread(()->{try{boolean saved=request(null).optBoolean("saved");a.runOnUiThread(()->status.setText(saved?"Key saved":"Using your current Qoder login"));}catch(Exception e){a.runOnUiThread(()->status.setText("Local service unavailable"));}}).start();
  android.view.View.OnClickListener action=v->{boolean deleting=v==remove;String value=key.getText().toString().trim();if(!deleting&&value.isEmpty()){status.setText("Enter a Qoder personal access token.");return;}save.setEnabled(false);remove.setEnabled(false);status.setText("Saving…");
   new Thread(()->{try{JSONObject body=new JSONObject();if(deleting)body.put("remove",true);else body.put("key",value);request(body);a.runOnUiThread(()->{key.setText("");status.setText(deleting?"Saved key removed. Reconnecting with your Qoder login…":"Key saved. Reconnecting localhost…");save.setEnabled(true);remove.setEnabled(true);});}catch(Exception e){a.runOnUiThread(()->{status.setText("Could not save the key. Check the local service.");save.setEnabled(true);remove.setEnabled(true);});}}).start();};save.setOnClickListener(action);remove.setOnClickListener(action);
 }
}
