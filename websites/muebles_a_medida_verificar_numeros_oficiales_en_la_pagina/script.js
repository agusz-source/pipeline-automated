// Scroll-triggered fade-in for key elements
const fadeTargets = [
    '.intro__text',
    '.midbreak__quote',
    '.testimonial',
    '.service',
    '.pcard',
];

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
        }
    });
}, {
    threshold: 0.1,
    rootMargin: '0px 0px -40px 0px',
});

document.querySelectorAll(fadeTargets.join(', ')).forEach((el, i) => {
    if (el.classList.contains('testimonial') || el.classList.contains('service') || el.classList.contains('pcard')) {
        el.style.transitionDelay = `${(i % 4) * 0.07}s`;
    }
    observer.observe(el);
});

// Sticky nav: add shadow on scroll
const nav = document.querySelector('.nav');
if (nav) {
    const updateNav = () => {
        nav.style.boxShadow = window.scrollY > 12
            ? '0 1px 14px rgba(16,47,82,0.09)'
            : 'none';
    };
    window.addEventListener('scroll', updateNav, { passive: true });
}

// WhatsApp bubble: hide when user is in contact section
const waBubble = document.querySelector('.wa-bubble');
const contactSection = document.querySelector('.contact');

if (waBubble && contactSection) {
    const contactObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            waBubble.style.opacity = entry.isIntersecting ? '0' : '1';
            waBubble.style.pointerEvents = entry.isIntersecting ? 'none' : 'auto';
        });
    }, { threshold: 0.3 });

    contactObserver.observe(contactSection);
}
