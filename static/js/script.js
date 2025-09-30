// static/js/script.js

document.addEventListener('DOMContentLoaded', function () {

    // --- CSRF Token ---
    // A single source for the CSRF token to be used in all API requests.
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;

    // --- Dynamic Form Items (Add/Remove for Resume Builder) ---
    // This makes the "Add another" buttons work for education, experience, etc.
    const setupDynamicItems = () => {
        document.querySelectorAll('.btn-add-item').forEach(button => {
            button.addEventListener('click', () => {
                const containerId = button.dataset.container;
                const templateId = button.dataset.template;
                const container = document.getElementById(containerId);
                const template = document.getElementById(templateId);

                if (container && template) {
                    const clone = template.content.cloneNode(true);
                    // Add a remove button to the cloned item
                    const removeBtn = document.createElement('button');
                    removeBtn.type = 'button';
                    removeBtn.className = 'btn btn-danger-secondary btn-remove-item';
                    removeBtn.innerHTML = '<i class="fas fa-trash-alt"></i> Remove';
                    clone.querySelector('.dynamic-item').appendChild(removeBtn);
                    container.appendChild(clone);
                }
            });
        });

        // Event delegation for removing items
        document.querySelector('.resume-form')?.addEventListener('click', (e) => {
            if (e.target && e.target.classList.contains('btn-remove-item')) {
                e.target.closest('.dynamic-item').remove();
            }
        });
    };
    setupDynamicItems(); // Call the function to set up the listeners.


    // --- AI Feature: About Us Mission Generator ---
    const generateAboutBtn = document.getElementById('generate-about-btn');
    if (generateAboutBtn) {
        generateAboutBtn.addEventListener('click', async () => {
            const resultsDiv = document.getElementById('ai-about-description');

            generateAboutBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
            generateAboutBtn.disabled = true;
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<div class="loader">Thinking... <i class="fas fa-spinner fa-spin"></i></div>';

            try {
                const response = await fetch('/api/generate-about', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();
                if (data.description) {
                    resultsDiv.innerHTML = `<p>${data.description.replace(/\n/g, '</p><p>')}</p>`;
                } else {
                    resultsDiv.innerHTML = `<p class="error">${data.error || 'An unknown error occurred.'}</p>`;
                }
            } catch (error) {
                console.error('Error:', error);
                resultsDiv.innerHTML = `<p class="error">An unexpected error occurred. Please try again.</p>`;
            } finally {
                generateAboutBtn.innerHTML = '<i class="fas fa-robot"></i> Let AI Describe Our Mission';
                generateAboutBtn.disabled = false;
            }
        });
    }


    // --- AI Feature: Resume Summary Expander ---
    const expandBtn = document.getElementById('expand-summary-btn');
    if (expandBtn) {
        expandBtn.addEventListener('click', async () => {
            const shortSummary = document.getElementById('summary-short').value;
            const fullSummaryTextarea = document.getElementById('summary-full');

            if (!shortSummary.trim()) {
                alert('Please write a short summary line first.');
                return;
            }

            expandBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
            expandBtn.disabled = true;

            try {
                const response = await fetch('/api/expand-summary', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ summary: shortSummary })
                });
                const data = await response.json();
                if (data.expanded_summary) {
                    fullSummaryTextarea.value = data.expanded_summary;
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred while contacting the AI. Please check the console.');
            } finally {
                expandBtn.innerHTML = '<i class="fas fa-magic"></i> Generate Full Summary with AI';
                expandBtn.disabled = false;
            }
        });
    }


    // --- Chatbot Functionality ---
    const chatbotIcon = document.getElementById('chatbot-icon');
    const chatbotPopup = document.getElementById('chatbot-popup');
    const closeChatbotBtn = document.getElementById('close-chatbot');
    const chatbotSendBtn = document.getElementById('chatbot-send');
    const chatbotInput = document.getElementById('chatbot-input');
    const chatbotBody = document.getElementById('chatbot-body');

    if (chatbotIcon) {
        chatbotIcon.addEventListener('click', () => chatbotPopup.classList.toggle('hidden'));
        closeChatbotBtn.addEventListener('click', () => chatbotPopup.classList.add('hidden'));

        const handleChat = async () => {
            const userMessage = chatbotInput.value.trim();
            if (!userMessage) return;

            // Display user message
            chatbotBody.innerHTML += `<div class="user-message">${userMessage}</div>`;
            chatbotInput.value = '';
            chatbotBody.scrollTop = chatbotBody.scrollHeight;

            // Get bot reply
            try {
                const response = await fetch('/api/chatbot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ message: userMessage })
                });
                const data = await response.json();
                chatbotBody.innerHTML += `<div class="bot-message">${data.reply}</div>`;
                chatbotBody.scrollTop = chatbotBody.scrollHeight;
            } catch (error) {
                chatbotBody.innerHTML += `<div class="bot-message">Sorry, I'm having trouble connecting.</div>`;
            }
        };

        chatbotSendBtn.addEventListener('click', handleChat);
        chatbotInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleChat();
        });
    }


    // --- Generic AI Tool Handler (for file uploads) ---
    // This single function powers all file-upload-based AI tools.
    const setupAiToolForm = (formId, apiUrl, resultsDivId) => {
        const form = document.getElementById(formId);
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const fileInput = form.querySelector('input[type="file"]');
                if (!fileInput.files || fileInput.files.length === 0) {
                    alert('Please select a PDF file to upload.');
                    return;
                }

                const formData = new FormData(form);
                const resultsDiv = document.getElementById(resultsDivId);
                const submitBtn = form.querySelector('button[type="submit"]');
                const originalBtnText = submitBtn.innerHTML;

                resultsDiv.style.display = 'block';
                resultsDiv.innerHTML = '<div class="loader">Analyzing... <i class="fas fa-spinner fa-spin"></i></div>';
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Working...';
                submitBtn.disabled = true;

                try {
                    // NOTE: Do NOT set 'Content-Type' header when using FormData with fetch.
                    // The browser sets it automatically with the correct boundary.
                    const response = await fetch(apiUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrfToken },
                        body: formData
                    });
                    const data = await response.json();
                    if (data.result) {
                        resultsDiv.innerHTML = data.result;
                    } else {
                        resultsDiv.innerHTML = `<p class="error">${data.error || 'An unknown error occurred.'}</p>`;
                    }
                } catch (error) {
                    console.error('Error:', error);
                    resultsDiv.innerHTML = `<p class="error">An unexpected error occurred. Please try again.</p>`;
                } finally {
                    submitBtn.innerHTML = originalBtnText;
                    submitBtn.disabled = false;
                }
            });
        }
    };

    // Initialize all AI tool forms by calling the setup function for each
    setupAiToolForm('resume-analyzer-form', '/api/analyze-resume', 'analysis-results');
    setupAiToolForm('cover-letter-form', '/api/generate-cover-letter', 'cover-letter-results');
    setupAiToolForm('job-matcher-form', '/api/match-jobs', 'job-matcher-results');
    setupAiToolForm('skill-gap-form', '/api/analyze-skill-gap', 'skill-gap-results');


    // --- Newsletter Subscription ---
    const newsletterBtn = document.getElementById('newsletter-btn');
    if (newsletterBtn) {
        newsletterBtn.addEventListener('click', () => {
            const emailInput = document.getElementById('newsletter-email');
            const email = emailInput.value;
            // Simple validation
            if (email && email.includes('@')) {
                alert('Thank you for subscribing!');
                emailInput.value = ''; // Clear input on success
            } else {
                alert('Please enter a valid email address.');
            }
        });
    }
});