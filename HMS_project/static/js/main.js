// ==============================
// HMS Project - Main JavaScript
// ==============================

document.addEventListener('DOMContentLoaded', function() {

    // ---------- Mobile Nav Toggle ----------
    const navToggle = document.querySelector('.nav-toggle');
    const navLinks = document.querySelector('.nav-links');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function() {
            navLinks.classList.toggle('open');
            // Animate hamburger
            const spans = navToggle.querySelectorAll('span');
            navToggle.classList.toggle('active');
        });

        // Close mobile nav on link click
        document.addEventListener('click', function(e) {
            if (!navToggle.contains(e.target) && !navLinks.contains(e.target)) {
                navLinks.classList.remove('open');
            }
        });
    }

    // ---------- Scroll to Top Button ----------
    const scrollTopBtn = document.querySelector('.scroll-top');
    if (scrollTopBtn) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 300) {
                scrollTopBtn.classList.add('visible');
            } else {
                scrollTopBtn.classList.remove('visible');
            }
        });

        scrollTopBtn.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // ---------- Auto-dismiss Messages ----------
    const messages = document.querySelectorAll('.message');
    messages.forEach(function(msg) {
        setTimeout(function() {
            msg.style.opacity = '0';
            msg.style.transform = 'translateX(40px)';
            setTimeout(function() {
                msg.remove();
            }, 300);
        }, 4000);

        const closeBtn = msg.querySelector('.close-msg');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                msg.style.opacity = '0';
                msg.style.transform = 'translateX(40px)';
                setTimeout(function() {
                    msg.remove();
                }, 300);
            });
        }
    });

    // ---------- Image Gallery Slider ----------
    const slider = document.querySelector('.gallery-slider');
    const prevBtn = document.querySelector('.gallery-nav.prev');
    const nextBtn = document.querySelector('.gallery-nav.next');

    if (slider && prevBtn && nextBtn) {
        let currentSlide = 0;
        const slides = slider.querySelectorAll('.gallery-slide');
        const totalSlides = slides.length;

        function updateSlider() {
            slider.style.transform = `translateX(-${currentSlide * 100}%)`;
        }

        nextBtn.addEventListener('click', function() {
            currentSlide = (currentSlide + 1) % totalSlides;
            updateSlider();
        });

        prevBtn.addEventListener('click', function() {
            currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
            updateSlider();
        });

        // Auto-slide every 5 seconds
        let autoSlide = setInterval(function() {
            currentSlide = (currentSlide + 1) % totalSlides;
            updateSlider();
        }, 5000);

        // Pause auto-slide on hover
        slider.parentElement.addEventListener('mouseenter', function() {
            clearInterval(autoSlide);
        });

        slider.parentElement.addEventListener('mouseleave', function() {
            autoSlide = setInterval(function() {
                currentSlide = (currentSlide + 1) % totalSlides;
                updateSlider();
            }, 5000);
        });
    }

    // ---------- Guest Counter ----------
    const counterBtns = document.querySelectorAll('.guest-counter button');
    counterBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            let value = parseInt(input.value) || 0;

            if (this.classList.contains('counter-minus')) {
                value = Math.max(0, value - 1);
            } else if (this.classList.contains('counter-plus')) {
                value = Math.min(10, value + 1);
            }

            input.value = value;
        });
    });

    // ---------- Heart/Wishlist Toggle ----------
    document.addEventListener('click', function(e) {
        if (e.target.closest('.heart-btn')) {
            const btn = e.target.closest('.heart-btn');
            btn.classList.toggle('liked');
            const icon = btn.querySelector('i');
            if (btn.classList.contains('liked')) {
                icon.className = 'fas fa-heart';
                btn.style.color = '#ef4444';
            } else {
                icon.className = 'far fa-heart';
                btn.style.color = '';
            }
        }
    });

    // ---------- Dropdown Keyboard Accessibility ----------
    const dropdowns = document.querySelectorAll('.nav-dropdown');
    dropdowns.forEach(function(dropdown) {
        const trigger = dropdown.querySelector('span');
        const menu = dropdown.querySelector('.nav-dropdown-menu');

        if (trigger) {
            trigger.addEventListener('click', function(e) {
                e.stopPropagation();
                // Close all other dropdowns
                dropdowns.forEach(function(d) {
                    if (d !== dropdown) {
                        d.classList.remove('active');
                    }
                });
                dropdown.classList.toggle('active');
            });
        }
    });

    // Close dropdowns on outside click
    document.addEventListener('click', function() {
        dropdowns.forEach(function(d) {
            d.classList.remove('active');
        });
    });

});
