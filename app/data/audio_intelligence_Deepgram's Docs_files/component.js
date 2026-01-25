// Fern's search is now hidden via CSS in styles.css

// insert <script type="text/javascript">
//   window.heapReadyCb=window.heapReadyCb||[],window.heap=window.heap||[],heap.load=function(e,t){window.heap.envId=e,window.heap.clientConfig=t=t||{},window.heap.clientConfig.shouldFetchServerConfig=!1;var a=document.createElement("script");a.type="text/javascript",a.async=!0,a.src="https://cdn.us.heap-api.com/config/"+e+"/heap_config.js";var r=document.getElementsByTagName("script")[0];r.parentNode.insertBefore(a,r);var n=["init","startTracking","stopTracking","track","resetIdentity","identify","getSessionId","getUserId","getIdentity","addUserProperties","addEventProperties","removeEventProperty","clearEventProperties","addAccountProperties","addAdapter","addTransformer","addTransformerFn","onReady","addPageviewProperties","removePageviewProperty","clearPageviewProperties","trackPageview"],i=function(e){return function(){var t=Array.prototype.slice.call(arguments,0);window.heapReadyCb.push({name:e,fn:function(){heap[e]&&heap[e].apply(heap,t)}})}};for(var p=0;p<n.length;p++)heap[n[p]]=i(n[p])};
//   heap.load("765739241");
// </script>

let kapaWidgetInserted = false;
let gradientBorderElement = null;

function isSidePanelOpen() {
  const panelWidth = parseInt(
    getComputedStyle(document.documentElement).getPropertyValue('--ask-ai-panel-width')
  );
  if (!isNaN(panelWidth) && panelWidth > 0) {
    return true;
  }
  return false;
}

function insertHeap() {
  if (document.getElementById("heap-script")) return;
  
  const script = document.createElement("script");
  script.setAttribute("id", "heap-script");
  script.type = "text/javascript";
  script.innerHTML = `
    window.heapReadyCb=window.heapReadyCb||[],window.heap=window.heap||[],heap.load=function(e,t){window.heap.envId=e,window.heap.clientConfig=t=t||{},window.heap.clientConfig.shouldFetchServerConfig=!1;var a=document.createElement("script");a.type="text/javascript",a.async=!0,a.src="https://cdn.us.heap-api.com/config/"+e+"/heap_config.js";var r=document.getElementsByTagName("script")[0];r.parentNode.insertBefore(a,r);var n=["init","startTracking","stopTracking","track","resetIdentity","identify","getSessionId","getUserId","getIdentity","addUserProperties","addEventProperties","removeEventProperty","clearEventProperties","addAccountProperties","addAdapter","addTransformer","addTransformerFn","onReady","addPageviewProperties","removePageviewProperty","clearPageviewProperties","trackPageview"],i=function(e){return function(){var t=Array.prototype.slice.call(arguments,0);window.heapReadyCb.push({name:e,fn:function(){heap[e]&&heap[e].apply(heap,t)}})}};for(var p=0;p<n.length;p++)heap[n[p]]=i(n[p])};
    heap.load("765739241");
  `;
  document.head.appendChild(script);
}

function insertKapaWidget() {
  if (kapaWidgetInserted) return;

  const gradientBorder = document.createElement("div");
  gradientBorder.setAttribute("id", "kapa-gradient-border");
  gradientBorder.style.position = "fixed";
  gradientBorder.style.bottom = "18px";
  gradientBorder.style.right = "18px";
  gradientBorder.style.height = "89px";
  gradientBorder.style.width = "89px";
  gradientBorder.style.background =
    "linear-gradient(90deg, #201CFF -91.5%, #13EF95 80.05%)";
  gradientBorder.style.borderRadius = "100rem";
  gradientBorder.style.boxShadow = "0px 4px 6px rgba(0, 0, 0, 0.1)";
  
  if (isSidePanelOpen()) {
    gradientBorder.style.display = "none";
  }

  const script = document.createElement("script");
  script.setAttribute("id", "kapa-widget-script");
  script.async = true;
  script.src = "https://widget.kapa.ai/kapa-widget.bundle.js";

  script.setAttribute("data-user-analytics-fingerprint-enabled", "true");
  script.setAttribute(
    "data-website-id",
    "f5c1c9d4-b072-4c91-8da2-231cc5ea31d2"
  );
  script.setAttribute("data-project-name", "Deepgram");
  script.setAttribute("data-modal-title", "Get AI Powered Help Using Deepgram");
  script.setAttribute("data-button-text", "✦ Ask AI");
  script.setAttribute("data-project-color", "#2C2C33");
  script.setAttribute("data-button-bg-color", "#1A1A1F");
  script.setAttribute("data-button-image-height", "0");
  script.setAttribute("data-button-image-width", "0");
  script.setAttribute("data-button-height", "85px");
  script.setAttribute("data-button-width", "85px");
  script.setAttribute("data-button-border-radius", "100rem");
  script.setAttribute("data-button-border", "0px solid #fff");
  script.setAttribute(
    "data-project-logo",
    "https://media.licdn.com/dms/image/D560BAQEaRN1vSzE2Ng/company-logo_200_200/0/1680904416780/deepgram_logo?e=2147483647&v=beta&t=YFDv1MdWVSsq1yknvJ0cD3Acvvi02d6pV1IDiUzA5MA"
  );
  script.setAttribute(
    "data-modal-disclaimer",
    "This is a custom LLM for answering questions about Deepgram. Answers are based on the contents of Deepgram's: Documentation, API reference, Code Samples, Help Center and SDKs."
  );

  document.body.appendChild(gradientBorder);
  document.head.appendChild(script);
  
  kapaWidgetInserted = true;
  gradientBorderElement = gradientBorder;
}

function hideKapaWidget() {
  if (gradientBorderElement) {
    gradientBorderElement.style.display = "none";
  }
  
  // Hide any Kapa widget related-elements
  const kapaElements = document.querySelectorAll('[id*="kapa"], [class*="kapa"]');
  kapaElements.forEach(el => {
    if (el.id.includes("kapa") || (el.className && el.className.includes && el.className.includes("kapa"))) {
      el.style.display = "none";
    }
  });
}

function showKapaWidget() {
  if (gradientBorderElement) {
    gradientBorderElement.style.display = "block";
  }
  
  // Show any Kapa widget related-elements
  const kapaElements = document.querySelectorAll('[id*="kapa"], [class*="kapa"]');
  kapaElements.forEach(el => {
    if (el.id.includes("kapa") || (el.className && el.className.includes && el.className.includes("kapa"))) {
      el.style.display = "";
    }
  });
}

function handlePanelChange() {
  if (isSidePanelOpen()) {
    hideKapaWidget();
  } else {
    showKapaWidget();
  }
}

function setupPanelObserver() {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
        handlePanelChange();
      }
    });
  });

  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['style']
  });

  return observer;
}

async function initializeComponents() {
  insertKapaWidget();
  insertHeap();
  
  setupPanelObserver();
}

if (
  document.readyState === "complete" ||
  document.readyState === "interactive"
) {
  initializeComponents();
} else {
  document.addEventListener("DOMContentLoaded", initializeComponents);
}