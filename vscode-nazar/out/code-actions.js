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
exports.NazarCodeActionProvider = void 0;
const vscode = __importStar(require("vscode"));
/**
 * Nazar Code Action Provider
 *
 * Nazar tarama sonuclarindaki how_to_fix verisini kullanarak
 * VS Code "Quick Fix" aksiyonlari olusturur.
 */
class NazarCodeActionProvider {
    diagnosticsProvider;
    static providedCodeActionKinds = [
        vscode.CodeActionKind.QuickFix,
    ];
    constructor(diagnosticsProvider) {
        this.diagnosticsProvider = diagnosticsProvider;
    }
    provideCodeActions(document, range, context, _token) {
        const actions = [];
        const results = this.diagnosticsProvider.getResultsForUri(document.uri);
        for (const diagnostic of context.diagnostics) {
            if (diagnostic.source !== 'nazar') {
                continue;
            }
            // subtype eslestirmesi ile sonucu bul
            const matchingResult = results.find(r => r.subtype === diagnostic.code);
            if (!matchingResult) {
                continue;
            }
            // Quick Fix: how_to_fix.quick_fix varsa text replacement olustur
            if (matchingResult.how_to_fix?.quick_fix) {
                const fixAction = this.createQuickFixAction(document, diagnostic, matchingResult);
                if (fixAction) {
                    actions.push(fixAction);
                }
            }
            // Bilgi aksiyonu: Cozum aciklamasi goster
            if (matchingResult.how_to_fix?.cozum) {
                const infoAction = this.createInfoAction(diagnostic, matchingResult);
                actions.push(infoAction);
            }
            // Rehber aksiyonu: Guide varsa rehber ac
            if (matchingResult.guide || matchingResult.subtype) {
                const guideAction = this.createGuideAction(diagnostic, matchingResult);
                actions.push(guideAction);
            }
        }
        return actions;
    }
    /**
     * Quick fix: Satiri how_to_fix.quick_fix ile degistir.
     */
    createQuickFixAction(document, diagnostic, result) {
        const quickFixText = result.how_to_fix?.quick_fix;
        if (!quickFixText) {
            return null;
        }
        const action = new vscode.CodeAction(`Nazar: Bu sorunu duzelt (${result.subtype})`, vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic];
        action.isPreferred = true;
        const edit = new vscode.WorkspaceEdit();
        const line = diagnostic.range.start.line;
        const fullLine = document.lineAt(line);
        // quick_fix icinde "REPLACE:" veya "INSERT:" yonergesi varsa isle
        if (quickFixText.startsWith('REPLACE:')) {
            const replacement = quickFixText.substring('REPLACE:'.length).trim();
            edit.replace(document.uri, fullLine.range, replacement);
        }
        else if (quickFixText.startsWith('INSERT_BEFORE:')) {
            const insertion = quickFixText.substring('INSERT_BEFORE:'.length).trim();
            edit.insert(document.uri, new vscode.Position(line, 0), insertion + '\n');
        }
        else if (quickFixText.startsWith('INSERT_AFTER:')) {
            const insertion = quickFixText.substring('INSERT_AFTER:'.length).trim();
            edit.insert(document.uri, new vscode.Position(line + 1, 0), insertion + '\n');
        }
        else if (quickFixText.startsWith('DELETE')) {
            edit.delete(document.uri, fullLine.rangeIncludingLineBreak);
        }
        else {
            // Varsayilan: satiri degistir
            edit.replace(document.uri, fullLine.range, quickFixText);
        }
        action.edit = edit;
        return action;
    }
    /**
     * Bilgi aksiyonu: Cozum aciklamasini bildirim olarak goster.
     */
    createInfoAction(diagnostic, result) {
        const action = new vscode.CodeAction(`Nazar: Cozum bilgisi - ${result.name}`, vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic];
        action.isPreferred = false;
        action.command = {
            command: 'vscode.window.showInformationMessage',
            title: 'Cozum Bilgisi',
            arguments: [
                `${result.how_to_fix?.sorun || result.name}\n\nCozum: ${result.how_to_fix?.cozum || 'Detay yok.'}`
            ],
        };
        // VS Code komut olarak bildirim gosteremez, kendi wrapper komutunu kullan
        action.command = {
            command: 'nazar.showFixInfo',
            title: 'Cozum Bilgisi',
            arguments: [result.how_to_fix?.sorun || result.name, result.how_to_fix?.cozum || 'Detay yok.'],
        };
        return action;
    }
    /**
     * Rehber aksiyonu: Nazar rehber panelini acar.
     */
    createGuideAction(diagnostic, result) {
        const subtype = result.subtype || 'unknown';
        const action = new vscode.CodeAction(`Nazar: "${subtype}" rehberini ac`, vscode.CodeActionKind.QuickFix);
        action.diagnostics = [diagnostic];
        action.isPreferred = false;
        // showGuide komutunu cagir
        action.command = {
            command: 'nazar.showGuide',
            title: 'Rehber Ac',
            arguments: [subtype],
        };
        return action;
    }
}
exports.NazarCodeActionProvider = NazarCodeActionProvider;
//# sourceMappingURL=code-actions.js.map