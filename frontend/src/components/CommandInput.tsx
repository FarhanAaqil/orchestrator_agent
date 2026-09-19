/**
 * frontend/src/components/CommandInput.tsx
 * Command entry component with accent-primary focus ring & button on surface-primary.
 */

import React, { useState } from 'react';
import { Send, Sparkles } from 'lucide-react';

interface CommandInputProps {
  onSubmit: (command: string) => void;
  isLoading?: boolean;
  placeholder?: string;
}

export const CommandInput: React.FC<CommandInputProps> = ({
  onSubmit,
  isLoading = false,
  placeholder = 'Type a command (e.g. "Tailor my resume for a Senior AI role at DeepMind")...',
}) => {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim() || isLoading) return;
    onSubmit(value.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="relative w-full">
      <div className="relative flex items-center bg-surface-primary rounded-2xl border border-surface-primary shadow-xl focus-within:ring-2 focus-within:ring-accent-primary focus-within:border-transparent transition-all">
        <Sparkles className="w-5 h-5 text-accent-primary ml-4 flex-shrink-0" />
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={isLoading}
          className="w-full bg-transparent text-text-primary px-4 py-4 text-base placeholder:text-text-muted focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!value.trim() || isLoading}
          className="mr-3 px-5 py-2.5 bg-accent-primary hover:bg-[#ffa343] text-text-onLight font-semibold text-sm rounded-pill flex items-center gap-2 transition-transform active:scale-95 disabled:opacity-40 disabled:pointer-events-none shadow-md"
        >
          {isLoading ? (
            <span className="inline-block w-4 h-4 border-2 border-text-onLight border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              <span>Execute</span>
              <Send className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
};
