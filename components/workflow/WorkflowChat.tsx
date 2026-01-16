'use client';

/**
 * WorkflowChat - AI chat panel for editing workflows.
 *
 * Features:
 * - Model selection (Anthropic/OpenAI)
 * - Conversation history maintained per session
 * - Sends current workflow definition as context
 * - Handles workflow updates from AI responses
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { X, Send, Settings, RefreshCw } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  definition?: Record<string, unknown>;
  definitionChanged?: boolean;
  renderCode?: string;
  renderCodeChanged?: boolean;
}

interface WorkflowChatProps {
  /** Current workflow definition */
  definition: Record<string, unknown>;
  /** Workflow definition ID - used to scope chat history */
  definitionId?: number | string;
  /** Opportunity ID - used to scope API requests */
  opportunityId?: number;
  /** Current render code */
  renderCode?: string;
  /** Callback when workflow definition is updated */
  onWorkflowUpdate: (newDefinition: Record<string, unknown>) => void;
  /** Callback when render code is updated */
  onRenderCodeUpdate?: (newRenderCode: string) => void;
  /** Callback to close the panel */
  onClose?: () => void;
  /** API URLs */
  submitUrl?: string;
  statusUrl?: string;
  historyUrl?: string;
}

const SESSION_STORAGE_KEY_PREFIX = 'workflow_chat_session_';
const MODEL_STORAGE_KEY = 'workflow_chat_model';

function getCSRFToken(): string {
  const tokenInput = document.querySelector<HTMLInputElement>(
    '[name=csrfmiddlewaretoken]',
  );
  return tokenInput ? tokenInput.value : '';
}

function getOrCreateSessionId(definitionId?: number | string): string {
  // Use workflow-specific session key if definitionId is provided
  const storageKey = definitionId
    ? `${SESSION_STORAGE_KEY_PREFIX}${definitionId}`
    : `${SESSION_STORAGE_KEY_PREFIX}default`;

  let sessionId = localStorage.getItem(storageKey);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(storageKey, sessionId);
  }
  return sessionId;
}

export function WorkflowChat({
  definition,
  definitionId,
  opportunityId,
  renderCode,
  onWorkflowUpdate,
  onRenderCodeUpdate,
  onClose,
  submitUrl = '/ai/demo/submit/',
  statusUrl = '/ai/demo/status/',
  historyUrl = '/ai/demo/history/',
}: WorkflowChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<
    'ready' | 'submitted' | 'polling' | 'error'
  >('ready');
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>('');
  const [modelProvider, setModelProvider] = useState<'anthropic' | 'openai'>(
    'anthropic',
  );
  const [showSettings, setShowSettings] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Initialize session - re-run when definitionId changes
  useEffect(() => {
    const sid = getOrCreateSessionId(definitionId);
    setSessionId(sid);

    // Load saved model preference
    const savedModel = localStorage.getItem(MODEL_STORAGE_KEY);
    if (savedModel === 'openai' || savedModel === 'anthropic') {
      setModelProvider(savedModel);
    }

    // Load message history for this workflow from LabsRecord
    loadHistory();

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [definitionId]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadHistory = async () => {
    // Use workflow-specific endpoint if definitionId is provided
    if (!definitionId) {
      console.log('No definitionId, skipping history load');
      return;
    }

    try {
      const response = await fetch(
        `/labs/workflow/api/${definitionId}/chat/history/`,
      );
      if (response.ok) {
        const data = await response.json();
        if (data.messages && Array.isArray(data.messages)) {
          setMessages(
            data.messages.map((m: { role: string; content: string }) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
            })),
          );
        }
      }
    } catch (e) {
      console.error('Failed to load chat history:', e);
    }
  };

  const pollTaskStatus = useCallback(
    (taskId: string) => {
      pollingRef.current = setInterval(async () => {
        try {
          const response = await fetch(`${statusUrl}?task_id=${taskId}`);
          const data = await response.json();

          if (data.complete) {
            // Stop polling
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }

            setStatus('ready');
            setIsSubmitting(false);

            // Handle the response
            if (data.result) {
              const assistantMessage: Message = {
                role: 'assistant',
                content: data.result.message || data.result,
              };

              // Check if workflow definition was updated
              if (data.result.definition_changed && data.result.definition) {
                assistantMessage.definition = data.result.definition;
                assistantMessage.definitionChanged = true;
                onWorkflowUpdate(data.result.definition);
              }

              // Check if render code was updated
              if (data.result.render_code_changed && data.result.render_code) {
                assistantMessage.renderCode = data.result.render_code;
                assistantMessage.renderCodeChanged = true;
                onRenderCodeUpdate?.(data.result.render_code);
              }

              setMessages((prev) => [...prev, assistantMessage]);
            }
          } else if (data.status === 'FAILURE') {
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
            setStatus('error');
            setError(data.error || 'Task failed');
            setIsSubmitting(false);
          }
        } catch (e) {
          console.error('Error polling task status:', e);
        }
      }, 1000);
    },
    [statusUrl, onWorkflowUpdate, onRenderCodeUpdate],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!input.trim() || isSubmitting) return;

    const userMessage = input.trim();
    setInput('');
    setIsSubmitting(true);
    setStatus('submitted');
    setError(null);

    // Add user message to chat
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);

    try {
      // Prepare the context with current workflow definition, render code, and IDs
      const currentCode = JSON.stringify({
        definition: definition,
        definition_id: definitionId,
        opportunity_id: opportunityId,
        render_code: renderCode,
        model_provider: modelProvider,
      });

      const formData = new FormData();
      formData.append('prompt', userMessage);
      formData.append('session_id', sessionId);
      formData.append('agent', 'workflow');
      formData.append('current_code', currentCode);

      const response = await fetch(submitUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCSRFToken(),
        },
        body: formData,
      });

      const data = await response.json();

      if (data.success && data.task_id) {
        setStatus('polling');
        pollTaskStatus(data.task_id);
      } else {
        setStatus('error');
        setError(data.error || 'Failed to submit');
        setIsSubmitting(false);
      }
    } catch (e) {
      console.error('Error submitting prompt:', e);
      setStatus('error');
      setError(String(e));
      setIsSubmitting(false);
    }
  };

  const handleModelChange = (model: 'anthropic' | 'openai') => {
    setModelProvider(model);
    localStorage.setItem(MODEL_STORAGE_KEY, model);
    setShowSettings(false);
  };

  const handleNewSession = async () => {
    // Clear chat history from LabsRecord
    if (definitionId) {
      try {
        await fetch(`/labs/workflow/api/${definitionId}/chat/clear/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCSRFToken(),
          },
        });
      } catch (e) {
        console.error('Failed to clear chat history:', e);
      }
    }

    // Also generate a new local session ID
    const newSessionId = crypto.randomUUID();
    const storageKey = definitionId
      ? `${SESSION_STORAGE_KEY_PREFIX}${definitionId}`
      : `${SESSION_STORAGE_KEY_PREFIX}default`;
    localStorage.setItem(storageKey, newSessionId);
    setSessionId(newSessionId);
    setMessages([]);
    setShowSettings(false);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-200 bg-gray-50">
        <h3 className="font-semibold text-gray-900">Workflow AI Editor</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Settings"
          >
            <Settings size={18} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
              title="Close"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="p-3 border-b border-gray-200 bg-gray-50 space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              AI Model
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => handleModelChange('anthropic')}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  modelProvider === 'anthropic'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Claude (Anthropic)
              </button>
              <button
                onClick={() => handleModelChange('openai')}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  modelProvider === 'openai'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                GPT-4 (OpenAI)
              </button>
            </div>
          </div>
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-800"
          >
            <RefreshCw size={14} />
            Start new conversation
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 text-sm py-8">
            <p className="mb-2">Ask me to edit your workflow!</p>
            <p className="text-xs text-gray-400 space-y-1">
              <span className="block">
                Try: "Remove the summary cards at the top"
              </span>
              <span className="block">
                Or: "Add a new status called 'On Hold'"
              </span>
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {(message.definitionChanged || message.renderCodeChanged) && (
                <div className="mt-2 pt-2 border-t border-gray-200 text-xs text-green-600 space-y-1">
                  {message.definitionChanged && (
                    <div>
                      <i className="fa-solid fa-check mr-1"></i>
                      Definition updated
                    </div>
                  )}
                  {message.renderCodeChanged && (
                    <div>
                      <i className="fa-solid fa-code mr-1"></i>
                      UI updated
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {isSubmitting && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-3 py-2 text-sm text-gray-500">
              <i className="fa-solid fa-spinner fa-spin mr-2"></i>
              Thinking...
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-gray-200">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe changes to make..."
            disabled={isSubmitting}
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={isSubmitting || !input.trim()}
            className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
      </form>
    </div>
  );
}

export default WorkflowChat;
