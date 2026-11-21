package in.etawahcafe.applications;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.net.Uri;
import android.view.View;
import android.webkit.*;
import android.widget.Toast;
import java.util.ArrayList;

public class Main extends Activity {
    // Set to the merchant's HTTPS origin (no trailing slash) for the deployed build.
    private static final String ORIGIN = "";
    private WebView web;
    private ValueCallback<Uri[]> picker;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener(){ public android.view.WindowInsets onApplyWindowInsets(View v, android.view.WindowInsets i){
            v.setPadding(i.getSystemWindowInsetLeft(),i.getSystemWindowInsetTop(),i.getSystemWindowInsetRight(),i.getSystemWindowInsetBottom());
            return i; }
        });
        setContentView(web);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView w, WebResourceRequest req){
                Uri u=req.getUrl();
                if (!"https".equals(u.getScheme())) return true;
                if (!ORIGIN.isEmpty() && ORIGIN.equals("https://"+u.getEncodedAuthority())) return false;
                if (req.isForMainFrame()) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,u)); }
                    catch(android.content.ActivityNotFoundException ex){Toast.makeText(Main.this,"ब्राउज़र उपलब्ध नहीं है",Toast.LENGTH_SHORT).show();}
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView w,ValueCallback<Uri[]> cb,FileChooserParams params){
                if(picker!=null) picker.onReceiveValue(null);
                picker=cb;
                Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/pdf","image/jpeg","image/png"});
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);
                try{startActivityForResult(i,10);}catch(android.content.ActivityNotFoundException ex){picker.onReceiveValue(null);picker=null;}
                return true;
            }
        });
        web.loadUrl(ORIGIN.isEmpty()?"file:///android_asset/index.html":ORIGIN+"/");
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request!=10 || picker==null)return;
        ArrayList<Uri> files=new ArrayList<>();
        if(result==RESULT_OK && data!=null){
            if(data.getClipData()!=null){
                for(int j=0;j<data.getClipData().getItemCount();j++) files.add(data.getClipData().getItemAt(j).getUri());
            }else if(data.getData()!=null)files.add(data.getData());
        }
        picker.onReceiveValue(files.isEmpty()?null:files.toArray(new Uri[0]));
        picker=null;
    }
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
}
