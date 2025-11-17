'use client';

import React, { useState, useEffect, useCallback } from 'react';
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
} from '@/components/ai-elements/prompt-input';

type MessageType = {
  role: 'user' | 'assistant';
  parts: Array<{ type: 'text'; text: string }>;
};

function getCSRFToken(): string {
  const tokenInput = document.querySelector<HTMLInputElement>(
    '[name=csrfmiddlewaretoken]',
  );
  return tokenInput ? tokenInput.value : '';
}

export function HelloWorld() {
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<
    'ready' | 'submitted' | 'streaming' | 'error'
  >('ready');
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(
    null,
  );

  // Get URLs from data attributes on the container
  const getStatusUrl = () => {
    const container = document.getElementById('react-demo-root');
    return container?.dataset.statusUrl || '/ai/demo/status/';
  };

  const getSubmitUrl = () => {
    const container = document.getElementById('react-demo-root');
    return container?.dataset.submitUrl || '/ai/demo/submit/';
  };

  const stopPolling = useCallback(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  }, [pollingInterval]);

  const pollTaskStatus = useCallback(
    (taskId: string) => {
      stopPolling();

      const interval = setInterval(async () => {
        try {
          const response = await fetch(`${getStatusUrl()}?task_id=${taskId}`);
          const data = await response.json();

          if (data.error) {
            stopPolling();
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
              return [
                ...newMessages,
                {
                  role: 'assistant',
                  parts: [
                    {
                      type: 'text',
                      text: resultText,
                    },
                  ],
                },
              ];
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
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              parts: [
                {
                  type: 'text',
                  text: 'Failed to check task status',
                },
              ],
            },
          ]);
        }
      }, 1000);

      setPollingInterval(interval);
    },
    [stopPolling],
  );

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

      try {
        const response = await fetch(getSubmitUrl(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCSRFToken(),
          },
          body: new URLSearchParams({
            prompt: prompt,
          }),
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

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages Container */}
      <div className="flex-1 flex flex-col gap-4 mb-4 min-h-[300px] max-h-[600px] overflow-y-auto px-1">
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
      </div>

      {/* Input - Fixed at bottom */}
      <div className="border-t pt-4">
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
              <PromptInputSubmit status={status} disabled={isSubmitting} />
            </PromptInputFooter>
          </PromptInput>
        </PromptInputProvider>
      </div>
    </div>
  );
}
