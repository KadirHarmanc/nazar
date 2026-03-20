"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const diagnostics_1 = require("./diagnostics");
const code_actions_1 = require("./code-actions");
let diagnostics;
let outputChannel;
let statusBarItem;
function activate(context) {
    // Output channel olustur
    outputChannel = vscode.window.createOutputChannel('Nazar');
    outputChannel.appendLine('[Nazar] Extension aktif edildi.');
    context.subscriptions.push(outputChannel);
    // Diagnostics olustur
    diagnostics = new diagnostics_1.NazarDiagnostics(context, outputChannel);
    // Status bar olustur
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(shield) Nazar';
    statusBarItem.tooltip = 'Nazar - Otonom Test Araci (Tara icin tikla)';
    statusBarItem.command = 'nazar.scanFile';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    // Code action provider kaydet
    const codeActionProvider = new code_actions_1.NazarCodeActionProvider(diagnostics);
    const supportedLanguages = [
        'javascript', 'typescript', 'javascriptreact', 'typescriptreact',
        'python', 'go', 'rust', 'dart', 'swift', 'kotlin', 'java',
    ];
    for (const lang of supportedLanguages) {
        context.subscriptions.push(vscode.languages.registerCodeActionsProvider({ language: lang, scheme: 'file' }, codeActionProvider, { providedCodeActionKinds: code_actions_1.NazarCodeActionProvider.providedCodeActionKinds }));
    }
    // --- Komut: nazar.scan (Proje tara) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.scan', async () => {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            vscode.window.showWarningMessage('Nazar: Acik bir proje klasoru yok.');
            return;
        }
        outputChannel.appendLine('[Nazar] Proje taramasi baslatiliyor...');
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Nazar: Proje taraniyor...',
            cancellable: false,
        }, async () => {
            const grade = await diagnostics.scanProject(workspaceFolder.uri);
            updateStatusBar(grade);
        });
    }));
    // --- Komut: nazar.scanFile (Aktif dosya tara) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.scanFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('Nazar: Acik bir dosya yok.');
            return;
        }
        outputChannel.appendLine(`[Nazar] Dosya taraniyor: ${editor.document.uri.fsPath}`);
        statusBarItem.text = '$(loading~spin) Nazar...';
        const grade = await diagnostics.scanFile(editor.document.uri);
        updateStatusBar(grade);
    }));
    // --- Komut: nazar.showReport (Rapor goster) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.showReport', () => {
        const report = diagnostics.getLastReport();
        if (!report) {
            vscode.window.showInformationMessage('Nazar: Henuz bir tarama yapilmadi.');
            return;
        }
        const panel = vscode.window.createWebviewPanel('nazarReport', 'Nazar Tarama Raporu', vscode.ViewColumn.Beside, { enableScripts: false });
        panel.webview.html = buildReportHTML(report);
        outputChannel.appendLine('[Nazar] Rapor goruntusu acildi.');
    }));
    // --- Komut: nazar.openStudio (Tarayici Studio ac) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.openStudio', () => {
        const port = vscode.workspace.getConfiguration('nazar').get('studioPort', 8080);
        const url = `http://localhost:${port}`;
        vscode.env.openExternal(vscode.Uri.parse(url));
        outputChannel.appendLine(`[Nazar] Studio aciliyor: ${url}`);
    }));
    // --- Komut: nazar.showGuide (Rehber goster) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.showGuide', (subtype) => {
        diagnostics.showGuide(subtype);
    }));
    // --- Komut: nazar.showFixInfo (Cozum bilgisi goster) ---
    context.subscriptions.push(vscode.commands.registerCommand('nazar.showFixInfo', (sorun, cozum) => {
        vscode.window.showInformationMessage(`${sorun}\n\nCozum: ${cozum}`);
    }));
    // --- Otomatik tarama: Dosya kaydetme ---
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(async (doc) => {
        const autoScan = vscode.workspace.getConfiguration('nazar').get('autoScan', true);
        if (!autoScan) {
            return;
        }
        if (!isSupported(doc)) {
            return;
        }
        outputChannel.appendLine(`[Nazar] Otomatik tarama (kaydetme): ${doc.uri.fsPath}`);
        statusBarItem.text = '$(loading~spin) Nazar...';
        const grade = await diagnostics.scanFile(doc.uri);
        updateStatusBar(grade);
    }));
    // --- Dosya acildiginda tara ---
    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument(async (doc) => {
        const autoScan = vscode.workspace.getConfiguration('nazar').get('autoScan', true);
        if (!autoScan) {
            return;
        }
        if (!isSupported(doc)) {
            return;
        }
        outputChannel.appendLine(`[Nazar] Otomatik tarama (dosya acma): ${doc.uri.fsPath}`);
        const grade = await diagnostics.scanFile(doc.uri);
        updateStatusBar(grade);
    }));
    // --- Mevcut acik editordeki dosyalari tara ---
    for (const editor of vscode.window.visibleTextEditors) {
        if (isSupported(editor.document)) {
            diagnostics.scanFile(editor.document.uri).then((grade) => {
                updateStatusBar(grade);
            });
        }
    }
    outputChannel.appendLine('[Nazar] Tum komutlar ve dinleyiciler kayit edildi.');
}
function isSupported(doc) {
    const supported = [
        'javascript', 'typescript', 'javascriptreact', 'typescriptreact',
        'python', 'go', 'rust', 'dart', 'swift', 'kotlin', 'java',
    ];
    return supported.includes(doc.languageId);
}
function updateStatusBar(grade) {
    if (!grade) {
        statusBarItem.text = '$(shield) Nazar';
        statusBarItem.tooltip = 'Nazar - Otonom Test Araci';
        return;
    }
    const gradeIcons = {
        'A+': '$(pass-filled)',
        'A': '$(pass-filled)',
        'B': '$(info)',
        'C': '$(warning)',
        'D': '$(error)',
        'F': '$(error)',
    };
    const icon = gradeIcons[grade] || '$(shield)';
    statusBarItem.text = `${icon} Nazar: ${grade}`;
    statusBarItem.tooltip = `Nazar - Son tarama notu: ${grade}`;
    if (grade === 'A+' || grade === 'A') {
        statusBarItem.backgroundColor = undefined;
    }
    else if (grade === 'C' || grade === 'D') {
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
    else if (grade === 'F') {
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    }
    else {
        statusBarItem.backgroundColor = undefined;
    }
}
function buildReportHTML(report) {
    const gradeColor = report.grade === 'A+' || report.grade === 'A'
        ? '#27ae60'
        : report.grade === 'B'
            ? '#f39c12'
            : '#e74c3c';
    const failedRows = report.results
        .filter(r => !r.passed)
        .map(r => `
            <tr>
                <td style="padding:6px 12px;border-bottom:1px solid #333;">${escapeHtml(r.name)}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #333;">${escapeHtml(r.type)}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #333;">${escapeHtml(r.priority)}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #333;">${escapeHtml(r.detail)}</td>
            </tr>`)
        .join('');
    return `<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; color: #ccc; background: #1e1e1e; }
h1 { color: #fff; }
.grade { font-size: 64px; font-weight: bold; color: ${gradeColor}; }
.stats { display: flex; gap: 32px; margin: 20px 0; }
.stat { text-align: center; }
.stat-value { font-size: 28px; font-weight: bold; color: #fff; }
.stat-label { font-size: 13px; color: #888; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; margin-top: 20px; }
th { text-align: left; padding: 8px 12px; border-bottom: 2px solid #555; color: #fff; }
</style>
</head>
<body>
<h1>Nazar Tarama Raporu</h1>
<div class="grade">${escapeHtml(report.grade)}</div>
<div class="stats">
    <div class="stat"><div class="stat-value">${report.score}%</div><div class="stat-label">Basari</div></div>
    <div class="stat"><div class="stat-value">${report.total}</div><div class="stat-label">Toplam Test</div></div>
    <div class="stat"><div class="stat-value">${report.passed}</div><div class="stat-label">Gecti</div></div>
    <div class="stat"><div class="stat-value">${report.failed}</div><div class="stat-label">Kaldi</div></div>
</div>
${report.failed > 0 ? `
<h2 style="color:#e74c3c;">Basarisiz Testler</h2>
<table>
<tr><th>Test</th><th>Tip</th><th>Oncelik</th><th>Detay</th></tr>
${failedRows}
</table>` : '<p style="color:#27ae60;">Tum testler gecti!</p>'}
</body>
</html>`;
}
function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
function deactivate() {
    if (diagnostics) {
        diagnostics.dispose();
    }
    if (outputChannel) {
        outputChannel.dispose();
    }
}
//# sourceMappingURL=extension.js.map