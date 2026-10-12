package com.qoder.share;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
/** Compatibility entry point: Qoder opens its original Sessions interface. */
public final class CloudCatalogActivity extends Activity {
 public void onCreate(Bundle state){
  super.onCreate(state);StartupBridge.ensure(this);
  startActivity(new Intent().setClassName(this,"com.qoder.mobile.MainActivity"));finish();
 }
}
