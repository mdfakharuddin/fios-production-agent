(function() {
    // Interceptor to capture Upwork API responses directly from the main page context
    // This allows us to get perfectly structured data instead of relying on DOM scraping

    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const response = await originalFetch.apply(this, args);
        try {
            const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
            if (url && typeof url === 'string' && (url.includes('/graphql') || url.includes('/messages/'))) {
                // Clone the response because the body can only be read once
                const clone = response.clone();
                clone.text().then(text => {
                    if (text && (text.includes('message') || text.includes('room'))) {
                        window.dispatchEvent(new CustomEvent('Upie_NETWORK_INTERCEPT', {
                            detail: {
                                url: url,
                                response: text,
                                source: 'fetch'
                            }
                        }));
                    }
                }).catch(err => {
                    // silent ignore
                });
            }
        } catch (e) {}
        
        return response;
    };

    const originalXHR = window.XMLHttpRequest;
    function CustomXHR() {
        const xhr = new originalXHR();
        xhr.addEventListener('load', function() {
            try {
                const url = xhr.responseURL || '';
                if (url && (url.includes('/graphql') || url.includes('/messages/'))) {
                    // Check if response text is accessible
                    if (xhr.responseType === '' || xhr.responseType === 'text') {
                        const text = xhr.responseText;
                        if (text && (text.includes('message') || text.includes('room'))) {
                            window.dispatchEvent(new CustomEvent('Upie_NETWORK_INTERCEPT', {
                                detail: {
                                    url: url,
                                    response: text,
                                    source: 'xhr'
                                }
                            }));
                        }
                    }
                }
            } catch (e) {
                // Ignore DOMException
            }
        });
        return xhr;
    }
    
    // Copy properties to maintain full compatibility
    for (const prop in originalXHR) {
        if (typeof originalXHR[prop] === 'function') {
            CustomXHR[prop] = originalXHR[prop].bind(originalXHR);
        } else {
            Object.defineProperty(CustomXHR, prop, {
                get: () => originalXHR[prop],
                set: (val) => { originalXHR[prop] = val; }
            });
        }
    }
    
    window.XMLHttpRequest = CustomXHR;

    console.log("Upie: Network Interceptor Initialized in MAIN World. Sniffing XHR/Fetch...");
})();
