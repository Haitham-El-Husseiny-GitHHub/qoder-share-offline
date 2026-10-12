package com.qoder.share;
import android.app.*;
import android.content.Intent;
import android.view.View;
import android.view.inputmethod.*;
import android.widget.*;
/** Import arbitrary SAF files, then insert their absolute paths into the native Qoder draft. */
public final class QoderAttachments {
 private static AttachmentPicker picker;
 private static Activity owner;
 public static void show(Activity a){
  View editor=a.getCurrentFocus();InputConnection connection=editor==null?null:editor.onCreateInputConnection(new EditorInfo());
  if(connection==null){Toast.makeText(a,"Tap the message field first, then open Attach files.",Toast.LENGTH_LONG).show();return;}
  if(picker!=null)picker.close();owner=a;
  LinearLayout box=new LinearLayout(a);box.setOrientation(1);box.setPadding(24,12,24,12);TextView status=new TextView(a);box.addView(status);
  picker=new AttachmentPicker(a,new AttachmentPicker.Host(){
   public String workspace(){return "/data/data/com.termux/files/home";}
   public String key(){return "qoder-selected-files";}
   public boolean busy(){return false;}
   public String endpoint(){return "http://127.0.0.1:8767/api/attachments";}
   public void changed(){}public void status(String message){status.setText(message);}
  },box,0xff263a2c);
  box.addView(picker.button());Button add=new Button(a);add.setText("Add to message");box.addView(add);
  AlertDialog dialog=new AlertDialog.Builder(a).setTitle("Attachments").setView(box).setNegativeButton("×",null).create();
  add.setOnClickListener(v->{if(picker.uploading()){status.setText("Wait for the file import to finish.");return;}String refs=picker.prompt(true);if(refs.isEmpty()){status.setText("Choose files first.");return;}dialog.dismiss();editor.requestFocus();editor.postDelayed(()->{InputConnection current=editor.onCreateInputConnection(new EditorInfo());if(current!=null&&current.commitText(refs,1)){picker.clear("qoder-selected-files");Toast.makeText(a,"Attachments added to your message",Toast.LENGTH_SHORT).show();}else Toast.makeText(a,"Tap the message field and try Add to message again. Your files are saved.",Toast.LENGTH_LONG).show();},200);});dialog.show();
 }
 public static boolean result(Activity a,int request,int result,Intent data){return a==owner&&picker!=null&&picker.result(request,result,data);}
}
