'use client';

import React from 'react';
import {
  Message,
  MessageContent,
  MessageResponse,
} from '@/components/ai-elements/message';

export function HelloWorld() {
  // Sample messages for demo
  const sampleMessages = [
    {
      role: 'user' as const,
      parts: [
        {
          type: 'text' as const,
          text: 'Hello! This is a demo of the AI message components.',
        },
      ],
    },
    {
      role: 'assistant' as const,
      parts: [
        {
          type: 'text' as const,
          text: "Hi there! 👋 I'm using the shadcn AI message components. They look great!",
        },
      ],
    },
    {
      role: 'user' as const,
      parts: [
        {
          type: 'text' as const,
          text: 'Can you show me how they handle different message types?',
        },
      ],
    },
    {
      role: 'assistant' as const,
      parts: [
        {
          type: 'text' as const,
          text: 'Absolutely! These components support text messages, and can be extended to handle other types like images, code blocks, and more.',
        },
      ],
    },
  ];

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        AI Message Components Demo
      </h2>
      <div className="flex flex-col gap-4">
        {sampleMessages.map(({ role, parts }, index) => (
          <Message from={role} key={index}>
            <MessageContent>
              {parts.map((part, i) => {
                switch (part.type) {
                  case 'text':
                    return (
                      <MessageResponse key={`${role}-${i}`}>
                        {part.text}
                      </MessageResponse>
                    );
                  default:
                    return null;
                }
              })}
            </MessageContent>
          </Message>
        ))}
      </div>
    </div>
  );
}
