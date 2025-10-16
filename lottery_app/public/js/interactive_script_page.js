frappe.ready(function () {
    const scriptSelect = document.getElementById('script-select');
    const paramsInput = document.getElementById('params');
    const runBtn = document.getElementById('run-btn');
    const outputPre = document.getElementById('output');

    async function loadScripts() {
        const res = await frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: "Script", fields: ["name", "title"], limit_page_length: 100 }
        });
        res.message.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.text = s.title || s.name;
            scriptSelect.appendChild(opt);
        });
    }

    runBtn.addEventListener('click', async () => {
        const script_name = scriptSelect.value;
        const params = paramsInput.value;
        outputPre.innerText = "Running...";
        try {
            const resp = await frappe.xcall('interactive_scripts_app.interactive_scripts.script_api.run_script', { script_name, params });
            if (resp.success) outputPre.innerText = resp.output || '(no output)';
            else outputPre.innerText = 'ERROR:\n' + (resp.error || JSON.stringify(resp));
        } catch (e) {
            outputPre.innerText = 'Call failed: ' + e;
        }
    });

    loadScripts();
});
