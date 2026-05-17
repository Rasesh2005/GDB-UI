export const themes = {
    "monokai": {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '75715e' },
            { token: 'keyword', foreground: 'f92672' },
            { token: 'variable', foreground: 'f8f8f2' },
            { token: 'string', foreground: 'e6db74' },
            { token: 'number', foreground: 'ae81ff' },
            { token: 'type', foreground: '66d9ef', fontStyle: 'italic' },
        ],
        colors: {
            'editor.background': '#272822',
            'editor.foreground': '#f8f8f2',
            'editorLineNumber.foreground': '#90908a',
            'editor.selectionBackground': '#49483e',
            'editor.inactiveSelectionBackground': '#414141',
        }
    },
    "dracula": {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '6272a4' },
            { token: 'keyword', foreground: 'ff79c6' },
            { token: 'string', foreground: 'f1fa8c' },
            { token: 'variable', foreground: 'f8f8f2' },
            { token: 'type', foreground: '8be9fd', fontStyle: 'italic' },
            { token: 'function', foreground: '50fa7b' },
        ],
        colors: {
            'editor.background': '#282a36',
            'editor.foreground': '#f8f8f2',
            'editorLineNumber.foreground': '#6272a4',
            'editor.selectionBackground': '#44475a',
        }
    },
    "one-dark": {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '5c6370' },
            { token: 'keyword', foreground: 'c678dd' },
            { token: 'string', foreground: '98c379' },
            { token: 'variable', foreground: 'e06c75' },
            { token: 'function', foreground: '61afef' },
        ],
        colors: {
            'editor.background': '#282c34',
            'editor.foreground': '#abb2bf',
            'editorLineNumber.foreground': '#4b5263',
            'editor.selectionBackground': '#3e4451',
        }
    },
    "github-light": {
        base: 'vs',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '6a737d' },
            { token: 'keyword', foreground: 'd73a49' },
            { token: 'string', foreground: '032f62' },
            { token: 'variable', foreground: 'e36209' },
        ],
        colors: {
            'editor.background': '#ffffff',
            'editor.foreground': '#24292e',
            'editorLineNumber.foreground': '#1b1f234d',
            'editor.selectionBackground': '#0366d640',
        }
    },
    "nord": {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '616e88' },
            { token: 'keyword', foreground: '81a1c1' },
            { token: 'string', foreground: 'a3be8c' },
            { token: 'variable', foreground: 'd8dee9' },
        ],
        colors: {
            'editor.background': '#2e3440',
            'editor.foreground': '#d8dee9',
            'editorLineNumber.foreground': '#4c566a',
            'editor.selectionBackground': '#434c5e',
        }
    },
    "solarized-dark": {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '586e75' },
            { token: 'keyword', foreground: '859900' },
            { token: 'string', foreground: '2aa198' },
            { token: 'variable', foreground: '268bd2' },
        ],
        colors: {
            'editor.background': '#002b36',
            'editor.foreground': '#839496',
            'editorLineNumber.foreground': '#586e75',
            'editor.selectionBackground': '#073642',
        }
    }
};
