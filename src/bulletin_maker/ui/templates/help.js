const printBtn = document.getElementById('print-btn');
if (printBtn) {
    printBtn.addEventListener('click', () => window.print());
}

const sections = document.querySelectorAll('.help-content section[id]');
const tocLinks = document.querySelectorAll('.help-toc a');

const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const id = entry.target.id;
        tocLinks.forEach((link) => {
            link.classList.toggle('active', link.getAttribute('href') === '#' + id);
        });
    });
}, { rootMargin: '-90px 0px -50% 0px' });

sections.forEach((section) => observer.observe(section));
