'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Message,
  MessageContent,
  MessageResponse,
} from '@/components/ai-elements/message';
import {
  PromptInput,
  PromptInputProvider,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputAttachments,
  PromptInputAttachment,
  PromptInputTools,
  PromptInputButton,
} from '@/components/ai-elements/prompt-input';
import { PlusIcon, X } from 'lucide-react';

type MessageType = {
  role: 'user' | 'assistant';
  parts: Array<{ type: 'text'; text: string }>;
};

const SESSION_STORAGE_KEY = 'ai_demo_session_id';

function getCSRFToken(): string {
  const tokenInput = document.querySelector<HTMLInputElement>(
    '[name=csrfmiddlewaretoken]',
  );
  return tokenInput ? tokenInput.value : '';
}

function getOrCreateSessionId(): string {
  let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }
  return sessionId;
}

interface ChatUIProps {
  containerId?: string;
  onClose?: () => void;
}

export function ChatUI({
  containerId = 'chat-widget-root',
  onClose,
}: ChatUIProps) {
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<
    'ready' | 'submitted' | 'streaming' | 'error'
  >('ready');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  // Get URLs from data attributes on the container
  const getStatusUrl = () => {
    const container = document.getElementById(containerId);
    return container?.dataset.statusUrl || '/ai/demo/status/';
  };

  const getSubmitUrl = () => {
    const container = document.getElementById(containerId);
    return container?.dataset.submitUrl || '/ai/demo/submit/';
  };

  const getHistoryUrl = () => {
    const container = document.getElementById(containerId);
    return container?.dataset.historyUrl || '/ai/demo/history/';
  };

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      isPollingRef.current = false;
    }
  }, []);

  const pollTaskStatus = useCallback(
    (taskId: string) => {
      // Stop any existing polling
      stopPolling();

      // Prevent multiple polling instances
      if (isPollingRef.current) {
        return;
      }

      isPollingRef.current = true;

      const interval = setInterval(async () => {
        // Double-check we should still be polling
        if (!isPollingRef.current) {
          clearInterval(interval);
          return;
        }

        try {
          const response = await fetch(`${getStatusUrl()}?task_id=${taskId}`);
          const data = await response.json();

          if (data.error) {
            stopPolling();
            setStatus('error');
            setIsSubmitting(false);
            setMessages((prev) => {
              // Only add error if we haven't already processed this task
              const lastMessage = prev[prev.length - 1];
              if (
                lastMessage?.role === 'assistant' &&
                lastMessage.parts[0]?.text === 'Thinking...'
              ) {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = {
                  role: 'assistant',
                  parts: [
                    {
                      type: 'text',
                      text: `Error: ${data.error}`,
                    },
                  ],
                };
                return newMessages;
              }
              return prev;
            });
            return;
          }

          if (data.complete) {
            stopPolling();
            setStatus('ready');
            setIsSubmitting(false);

            const resultText =
              data.result !== undefined && data.result !== null
                ? typeof data.result === 'string'
                  ? data.result
                  : data.result?.message || JSON.stringify(data.result)
                : data.message || 'Task completed';

            setMessages((prev) => {
              // Replace the "Thinking..." message with the actual result
              // Only do this once - check if we've already processed this
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (
                lastMessage?.role === 'assistant' &&
                lastMessage.parts[0]?.text === 'Thinking...'
              ) {
                newMessages[newMessages.length - 1] = {
                  role: 'assistant',
                  parts: [
                    {
                      type: 'text',
                      text: resultText,
                    },
                  ],
                };
                return newMessages;
              }
              // If "Thinking..." was already replaced, don't add another message
              return newMessages;
            });
          } else if (data.message) {
            setStatus('streaming');
            // Optionally show progress message
          }
        } catch (error) {
          console.error('Polling error:', error);
          stopPolling();
          setStatus('error');
          setIsSubmitting(false);
          setMessages((prev) => {
            // Only add error if we haven't already processed this
            const lastMessage = prev[prev.length - 1];
            if (
              lastMessage?.role === 'assistant' &&
              lastMessage.parts[0]?.text === 'Thinking...'
            ) {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                role: 'assistant',
                parts: [
                  {
                    type: 'text',
                    text: 'Failed to check task status',
                  },
                ],
              };
              return newMessages;
            }
            return prev;
          });
        }
      }, 1000);

      pollingIntervalRef.current = interval;
    },
    [stopPolling],
  );

  const handleNewChat = useCallback(() => {
    // Clear session ID from localStorage
    localStorage.removeItem(SESSION_STORAGE_KEY);
    // Generate a new session ID
    const newSessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
    // Reset state
    setSessionId(newSessionId);
    setMessages([]);
    setStatus('ready');
    setIsSubmitting(false);
    // Stop any ongoing polling
    stopPolling();
  }, [stopPolling]);

  const handleSubmit = useCallback(
    async (message: { text: string; files: any[] }, event: React.FormEvent) => {
      event.preventDefault();

      const prompt = message.text.trim();
      if (!prompt) {
        return;
      }

      // Add user message
      setMessages((prev) => [
        ...prev,
        {
          role: 'user',
          parts: [
            {
              type: 'text',
              text: prompt,
            },
          ],
        },
      ]);

      setIsSubmitting(true);
      setStatus('submitted');

      // Get or create session ID
      const currentSessionId = sessionId || getOrCreateSessionId();
      if (!sessionId) {
        setSessionId(currentSessionId);
      }

      try {
        // Extract program_id from URL params if available
        const urlParams = new URLSearchParams(window.location.search);
        const programId = urlParams.get('program_id');

        const bodyParams: Record<string, string> = {
          prompt: prompt,
          session_id: currentSessionId,
        };

        if (programId) {
          bodyParams.program_id = programId;
        }

        const response = await fetch(getSubmitUrl(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCSRFToken(),
          },
          body: new URLSearchParams(bodyParams),
        });

        const data = await response.json();

        if (data.error) {
          setStatus('error');
          setIsSubmitting(false);
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              parts: [
                {
                  type: 'text',
                  text: `Error: ${data.error}`,
                },
              ],
            },
          ]);
          return;
        }

        if (data.task_id) {
          // Update session_id if returned from server
          if (data.session_id && data.session_id !== currentSessionId) {
            setSessionId(data.session_id);
            localStorage.setItem(SESSION_STORAGE_KEY, data.session_id);
          }

          setStatus('streaming');
          // Add a loading message
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              parts: [
                {
                  type: 'text',
                  text: 'Thinking...',
                },
              ],
            },
          ]);
          pollTaskStatus(data.task_id);
        }
      } catch (error) {
        console.error('Submit error:', error);
        setStatus('error');
        setIsSubmitting(false);
        setMessages((prev) => {
          // Remove the loading message and add error
          const newMessages = [...prev];
          if (
            newMessages[newMessages.length - 1]?.parts[0]?.text ===
            'Thinking...'
          ) {
            newMessages.pop();
          }
          return [
            ...newMessages,
            {
              role: 'assistant',
              parts: [
                {
                  type: 'text',
                  text: 'Failed to submit task',
                },
              ],
            },
          ];
        });
      }
    },
    [pollTaskStatus],
  );

  // Initialize session ID and load history on mount
  useEffect(() => {
    const currentSessionId = getOrCreateSessionId();
    setSessionId(currentSessionId);

    // Load message history if session exists
    const loadHistory = async () => {
      try {
        const response = await fetch(
          `${getHistoryUrl()}?session_id=${currentSessionId}`,
        );
        const data = await response.json();

        if (data.success && data.messages && data.messages.length > 0) {
          // Convert backend message format to frontend format
          const loadedMessages: MessageType[] = data.messages.map(
            (msg: { role: string; content: string }) => ({
              role: msg.role as 'user' | 'assistant',
              parts: [
                {
                  type: 'text' as const,
                  text: msg.content,
                },
              ],
            }),
          );
          setMessages(loadedMessages);
        }
      } catch (error) {
        console.error('Error loading history:', error);
        // Silently fail - it's okay if history doesn't load
      }
    };

    loadHistory();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop =
        messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus textarea after submission completes
  useEffect(() => {
    if (!isSubmitting && status === 'ready') {
      // Small delay to ensure the textarea is re-enabled
      const timer = setTimeout(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>(
          `#${containerId} textarea[name="message"]`,
        );
        if (textarea) {
          textarea.focus();
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isSubmitting, status, containerId]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages Container */}
      <div
        ref={messagesContainerRef}
        className="flex-1 flex flex-col gap-4 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <p className="text-sm">
                Start a conversation by typing a message below
              </p>
            </div>
          </div>
        ) : (
          messages.map(({ role, parts }, index) => {
            // Check if this is a loading message that should be replaced
            const isLastMessage = index === messages.length - 1;
            const isLoadingMessage =
              isLastMessage &&
              role === 'assistant' &&
              parts[0]?.text === 'Thinking...' &&
              status === 'streaming';

            return (
              <Message from={role} key={index}>
                <MessageContent>
                  {parts.map((part, i) => {
                    switch (part.type) {
                      case 'text':
                        return (
                          <MessageResponse key={`${role}-${i}`}>
                            {isLoadingMessage ? 'Thinking...' : part.text}
                          </MessageResponse>
                        );
                      default:
                        return null;
                    }
                  })}
                </MessageContent>
              </Message>
            );
          })
        )}
        {/* Invisible element to scroll to */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input - Fixed at bottom */}
      <div className="border-t p-4">
        <PromptInputProvider>
          <PromptInput onSubmit={handleSubmit} className="w-full">
            <PromptInputAttachments>
              {(attachment) => <PromptInputAttachment data={attachment} />}
            </PromptInputAttachments>
            <PromptInputBody>
              <PromptInputTextarea
                placeholder="Type your message here..."
                disabled={isSubmitting}
              />
            </PromptInputBody>
            <PromptInputFooter>
              <PromptInputTools>
                <PromptInputButton onClick={handleNewChat} type="button">
                  <PlusIcon size={16} />
                  <span>New Chat</span>
                </PromptInputButton>
                {onClose && (
                  <PromptInputButton onClick={onClose} type="button">
                    <X size={16} />
                    <span>Close</span>
                  </PromptInputButton>
                )}
              </PromptInputTools>
              <PromptInputSubmit status={status} disabled={isSubmitting} />
            </PromptInputFooter>
          </PromptInput>
        </PromptInputProvider>
      </div>
    </div>
  );
}
