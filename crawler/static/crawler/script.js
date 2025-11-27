document.addEventListener('DOMContentLoaded', () => {
    // Initialize all interactive features
    initFormHandling();
    initTypingEffect();
    initMatrixRain();
    initCodeStream();
    initTableAnimations();
    initParticles();
    initTerminalEffect();
    initStatusPulse();
});

// Form submission with loading state
function initFormHandling() {
    const form = document.querySelector('[data-loading-form]');
    if (!form) return;

    const loadingIndicator = form.querySelector('[data-loading-indicator]');
    const submitButton = form.querySelector('[data-loading-button]');

    form.addEventListener('submit', (e) => {
        if (loadingIndicator) {
            loadingIndicator.hidden = false;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.dataset.originalText = submitButton.textContent;
            submitButton.textContent = 'INITIALIZING...';
            
            // Simulate progress text changes
            let progress = 0;
            const progressTexts = [
                'SCANNING NETWORK...',
                'ESTABLISHING CONNECTION...',
                'PARSING DOCUMENTS...',
                'EXTRACTING DATA...'
            ];
            
            const progressInterval = setInterval(() => {
                if (progress < progressTexts.length) {
                    submitButton.textContent = progressTexts[progress];
                    progress++;
                }
            }, 1500);
            
            // Store interval ID to clear it if needed
            submitButton.dataset.progressInterval = progressInterval;
        }

        // Add ripple effect
        createRipple(e, submitButton);
    });

    // Add input validation indicators
    const inputs = form.querySelectorAll('input[required]');
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            if (input.value.trim()) {
                input.style.borderColor = 'var(--primary-green)';
                input.style.boxShadow = '0 0 10px rgba(0, 255, 65, 0.2)';
            } else {
                input.style.borderColor = 'var(--border-color)';
                input.style.boxShadow = 'none';
            }
        });
    });
}

// Typing effect for headings
function initTypingEffect() {
    const headings = document.querySelectorAll('.card h2');
    
    headings.forEach((heading, index) => {
        const text = heading.textContent;
        heading.textContent = '';
        heading.style.opacity = '1';
        
        // Delay based on card position
        setTimeout(() => {
            let charIndex = 0;
            const typingInterval = setInterval(() => {
                if (charIndex < text.length) {
                    heading.textContent += text.charAt(charIndex);
                    charIndex++;
                    
                    // Add cursor blink effect
                    if (charIndex === text.length) {
                        heading.style.borderRight = 'none';
                    }
                } else {
                    clearInterval(typingInterval);
                }
            }, 50);
        }, index * 200);
    });
}

// Matrix-style rain effect (lighter version)
// function initMatrixRain() {
//     const canvas = document.createElement('canvas');
//     canvas.className = 'matrix-canvas';
//     document.body.appendChild(canvas);

//     const ctx = canvas.getContext('2d');
//     canvas.width = window.innerWidth;
//     canvas.height = window.innerHeight;

//     const chars = '0101<>[]{}#%?=+*//::;';
//     const fontSize = 16;
//     const columns = canvas.width / fontSize;
//     const drops = Array(Math.floor(columns)).fill(1);

//     function drawMatrix() {
//         ctx.fillStyle = 'rgba(10, 14, 39, 0.06)';
//         ctx.fillRect(0, 0, canvas.width, canvas.height);

//         ctx.fillStyle = '#00ff6a';
//         ctx.shadowColor = 'rgba(0, 255, 65, 0.7)';
//         ctx.shadowBlur = 14;
//         ctx.font = `${fontSize}px monospace`;

//         for (let i = 0; i < drops.length; i++) {
//             const text = chars[Math.floor(Math.random() * chars.length)];
//             ctx.fillText(text, i * fontSize, drops[i] * fontSize);

//             if (drops[i] * fontSize > canvas.height && Math.random() > 0.94) {
//                 drops[i] = 0;
//             }
//             drops[i]++;
//         }
//     }

//     setInterval(drawMatrix, 50);

//     // Resize handler
//     window.addEventListener('resize', () => {
//         canvas.width = window.innerWidth;
//         canvas.height = window.innerHeight;
//     });
// }

function initMatrixRain() {
    const canvas = document.createElement('canvas');
    canvas.className = 'matrix-canvas';
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    // More diverse hacker-style characters
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$+-*/=%"\'#&_(){}[]|<>^~:;?!@'.split('');
    const fontSize = 18; // Increased from 16
    const columns = canvas.width / fontSize;
    const drops = Array(Math.floor(columns)).fill(1);
    
    // Track character trails for fade effect
    const trails = Array(Math.floor(columns)).fill(null).map(() => []);

    function drawMatrix() {
        // Darker trail fade for better contrast
        ctx.fillStyle = 'rgba(10, 14, 39, 0.08)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.font = `bold ${fontSize}px "Courier New", monospace`;

        for (let i = 0; i < drops.length; i++) {
            const text = chars[Math.floor(Math.random() * chars.length)];
            const x = i * fontSize;
            const y = drops[i] * fontSize;
            
            // Draw trailing characters with fade
            if (trails[i].length > 0) {
                trails[i].forEach((trail, idx) => {
                    const alpha = 1 - (idx / 15); // Fade over 15 characters
                    ctx.fillStyle = `rgba(0, 255, 106, ${alpha * 0.4})`;
                    ctx.shadowBlur = 0;
                    ctx.fillText(trail.char, trail.x, trail.y);
                });
            }

            // Bright leading character with strong glow
            ctx.fillStyle = '#00ff6a';
            ctx.shadowColor = 'rgba(0, 255, 106, 0.9)';
            ctx.shadowBlur = 20;
            ctx.fillText(text, x, y);

            // Add to trail
            trails[i].unshift({ char: text, x, y });
            if (trails[i].length > 15) {
                trails[i].pop();
            }

            // Reset drop at bottom with some randomness
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.92) {
                drops[i] = 0;
                trails[i] = [];
            }
            drops[i]++;
        }
    }

    const interval = setInterval(drawMatrix, 45);

    // Resize handler
    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        // Recalculate columns
        const newColumns = Math.floor(canvas.width / fontSize);
        drops.length = newColumns;
        trails.length = newColumns;
        drops.fill(1);
        trails.fill(null);
        for (let i = 0; i < newColumns; i++) {
            trails[i] = [];
        }
    });
}

// Floating code columns for a more visible background
// function initCodeStream() {
//     const stream = document.createElement('div');
//     stream.className = 'code-stream';
//     document.body.appendChild(stream);

//     const glyphs = ['0', '1', '{', '}', '/', '<', '>', '*', '#', '%', '=', '+'];
//     let columns = [];

//     const makeLine = () => {
//         const length = Math.floor(18 + Math.random() * 18);
//         return Array.from({ length }, () => glyphs[Math.floor(Math.random() * glyphs.length)]).join(' ');
//     };

//     const renderColumns = () => {
//         stream.innerHTML = '';
//         columns = [];
//         const count = Math.min(32, Math.max(14, Math.floor(window.innerWidth / 85)));

//         for (let i = 0; i < count; i++) {
//             const col = document.createElement('div');
//             col.className = 'code-column';
//             col.style.left = `${(i / count) * 100}%`;
//             col.style.animationDuration = `${6 + Math.random() * 7}s`;
//             col.style.animationDelay = `${Math.random() * 4}s`;
//             col.textContent = makeLine();
//             stream.appendChild(col);
//             columns.push(col);
//         }
//     };

//     renderColumns();
//     setInterval(() => columns.forEach(col => col.textContent = makeLine()), 1400);
//     window.addEventListener('resize', renderColumns);
// }


function initCodeStream() {
    const stream = document.createElement('div');
    stream.className = 'code-stream';
    document.body.appendChild(stream);

    // More varied hacker-style snippets
    const codeSnippets = [
        'SYSTEM_ACCESS_GRANTED',
        'FIREWALL_BYPASS',
        'ROOT_PRIVILEGE',
        'ENCRYPTION_KEYS',
        'NETWORK_SCAN',
        'PORT_22_OPEN',
        'SSH_TUNNEL',
        'PROXY_ACTIVE',
        'VPN_CONNECTED',
        'DATA_MINING',
        '0x4A8F9C2E',
        '192.168.1.1',
        'KERNEL_MODE',
        'BACKDOOR_INIT',
        'SHELL_ACCESS'
    ];
    
    const glyphs = ['0', '1', '{', '}', '/', '<', '>', '*', '#', '%', '=', '+', '[', ']', '|', '&', '$'];
    let columns = [];

    const makeLine = () => {
        // Mix of code snippets and random glyphs
        if (Math.random() > 0.6) {
            return codeSnippets[Math.floor(Math.random() * codeSnippets.length)];
        } else {
            const length = Math.floor(12 + Math.random() * 15);
            return Array.from({ length }, () => glyphs[Math.floor(Math.random() * glyphs.length)]).join(' ');
        }
    };

    const renderColumns = () => {
        stream.innerHTML = '';
        columns = [];
        const count = Math.min(28, Math.max(12, Math.floor(window.innerWidth / 95)));

        for (let i = 0; i < count; i++) {
            const col = document.createElement('div');
            col.className = 'code-column';
            col.style.left = `${(i / count) * 100}%`;
            col.style.animationDuration = `${7 + Math.random() * 8}s`;
            col.style.animationDelay = `${Math.random() * 5}s`;
            col.textContent = makeLine();
            stream.appendChild(col);
            columns.push(col);
        }
    };

    renderColumns();
    setInterval(() => columns.forEach(col => col.textContent = makeLine()), 1600);
    window.addEventListener('resize', renderColumns);
}

// Table row animations
function initTableAnimations() {
    const rows = document.querySelectorAll('.documents-table tbody tr');
    
    rows.forEach((row, index) => {
        row.style.opacity = '0';
        row.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            row.style.transition = 'all 0.5s ease';
            row.style.opacity = '1';
            row.style.transform = 'translateX(0)';
        }, index * 100);

        // Add click ripple effect
        row.addEventListener('click', (e) => {
            createRipple(e, row);
        });
    });
}

// Particle effect on hover
function initParticles() {
    const cards = document.querySelectorAll('.card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', (e) => {
            createParticles(e, card);
        });
    });
}

function createParticles(e, element) {
    const rect = element.getBoundingClientRect();
    const particleCount = 5;
    
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.style.position = 'absolute';
        particle.style.width = '4px';
        particle.style.height = '4px';
        particle.style.background = 'var(--primary-green)';
        particle.style.borderRadius = '50%';
        particle.style.pointerEvents = 'none';
        particle.style.left = e.clientX - rect.left + 'px';
        particle.style.top = e.clientY - rect.top + 'px';
        particle.style.boxShadow = '0 0 10px var(--primary-green)';
        
        element.appendChild(particle);
        
        const angle = (Math.PI * 2 * i) / particleCount;
        const velocity = 2;
        const vx = Math.cos(angle) * velocity;
        const vy = Math.sin(angle) * velocity;
        
        let x = 0;
        let y = 0;
        let opacity = 1;
        
        const animateParticle = () => {
            x += vx;
            y += vy;
            opacity -= 0.02;
            
            particle.style.transform = `translate(${x}px, ${y}px)`;
            particle.style.opacity = opacity;
            
            if (opacity > 0) {
                requestAnimationFrame(animateParticle);
            } else {
                particle.remove();
            }
        };
        
        requestAnimationFrame(animateParticle);
    }
}

// Ripple effect
function createRipple(e, element) {
    const ripple = document.createElement('div');
    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = e.clientX - rect.left - size / 2;
    const y = e.clientY - rect.top - size / 2;
    
    ripple.style.position = 'absolute';
    ripple.style.width = size + 'px';
    ripple.style.height = size + 'px';
    ripple.style.borderRadius = '50%';
    ripple.style.background = 'rgba(0, 255, 65, 0.3)';
    ripple.style.left = x + 'px';
    ripple.style.top = y + 'px';
    ripple.style.pointerEvents = 'none';
    ripple.style.transform = 'scale(0)';
    ripple.style.transition = 'transform 0.6s ease, opacity 0.6s ease';
    ripple.style.opacity = '1';
    
    element.style.position = 'relative';
    element.style.overflow = 'hidden';
    element.appendChild(ripple);
    
    setTimeout(() => {
        ripple.style.transform = 'scale(2)';
        ripple.style.opacity = '0';
    }, 10);
    
    setTimeout(() => ripple.remove(), 600);
}

// Terminal-style console messages
function initTerminalEffect() {
    const messages = [
        '> System initialized...',
        '> Connecting to scraper module...',
        '> Ready for operation',
    ];
    
    let messageIndex = 0;
    
    const showMessage = () => {
        if (messageIndex < messages.length) {
            console.log('%c' + messages[messageIndex], 
                'color: #00ff41; font-family: monospace; font-size: 12px;');
            messageIndex++;
            setTimeout(showMessage, 500);
        }
    };
    
    showMessage();
}

// Pulse the status bar to feel more like a live console
function initStatusPulse() {
    const statusBar = document.querySelector('[data-status-bar]');
    const statusValue = document.querySelector('[data-system-status]');
    if (!statusBar || !statusValue) return;

    const signal = document.createElement('div');
    signal.className = 'status-signal';
    statusBar.appendChild(signal);

    const modes = ['ONLINE', 'LISTENING', 'ARMED'];
    let index = 0;

    const tick = () => {
        index = (index + 1) % modes.length;
        statusValue.textContent = modes[index];
        statusBar.classList.toggle('status-glow');
        signal.style.width = `${60 + Math.random() * 40}%`;
        signal.style.opacity = `${0.4 + Math.random() * 0.4}`;
    };

    tick();
    setInterval(tick, 3200);
}

// Add glitch effect on logo hover
document.addEventListener('DOMContentLoaded', () => {
    const logo = document.querySelector('.logo a');
    if (logo) {
        logo.addEventListener('mouseenter', () => {
            let glitchCount = 0;
            const glitchInterval = setInterval(() => {
                logo.style.textShadow = `
                    ${Math.random() * 10 - 5}px ${Math.random() * 10 - 5}px 0 #ff0055,
                    ${Math.random() * 10 - 5}px ${Math.random() * 10 - 5}px 0 #00ff41,
                    ${Math.random() * 10 - 5}px ${Math.random() * 10 - 5}px 0 #0099ff
                `;
                glitchCount++;
                if (glitchCount > 5) {
                    clearInterval(glitchInterval);
                    logo.style.textShadow = '0 0 10px var(--primary-green)';
                }
            }, 50);
        });
    }
});

// Scan line effect for summary items
const summaryItems = document.querySelectorAll('.summary-list > div');
summaryItems.forEach((item, index) => {
    setTimeout(() => {
        item.style.opacity = '0';
        item.style.transform = 'translateY(10px)';
        item.style.transition = 'all 0.5s ease';
        
        requestAnimationFrame(() => {
            item.style.opacity = '1';
            item.style.transform = 'translateY(0)';
        });
    }, index * 100);
});