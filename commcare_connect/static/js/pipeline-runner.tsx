/**
 * Pipeline Runner - Webpack entry point for rendering custom data pipelines.
 *
 * This script:
 * 1. Loads pipeline data from the DOM and SSE stream
 * 2. Renders pipeline using dynamic React components (AI-generated code)
 * 3. Includes AI chat panel for editing pipelines
 * 4. Shows SQL preview for debugging
 * 5. Provides controls for saving/discarding changes
 */

import React, {
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from 'react';
import { createRoot } from 'react-dom/client';
import {
  MessageCircle,
  Code,
  Save,
  RotateCcw,
  X,
  Check,
  Database,
  Copy,
  ChevronDown,
  ChevronUp,
  RefreshCw,
} from 'lucide-react';

// Type definitions
interface PipelineDefinition {
  id: number;
  name: string;
  description: string;
  schema: PipelineSchema;
  render_code_id?: number;
}

interface PipelineSchema {
  name?: string;
  description?: string;
  version?: number;
  grouping_key: string;
  terminal_stage: 'visit_level' | 'aggregated';
  linking_field?: string;
  fields: FieldDefinition[];
  histograms?: HistogramDefinition[];
  filters?: Record<string, unknown>;
}

interface FieldDefinition {
  name: string;
  path?: string;
  paths?: string[];
  aggregation: string;
  transform?: string;
  description?: string;
  default?: unknown;
}

interface HistogramDefinition {
  name: string;
  path: string;
  paths?: string[];
  lower_bound: number;
  upper_bound: number;
  num_bins: number;
  bin_name_prefix?: string;
  transform?: string;
  description?: string;
}

interface PipelineData {
  rows: PipelineRow[];
  metadata: Record<string, unknown>;
  from_cache?: boolean;
}

interface PipelineRow {
  username: string;
  visit_date?: string;
  status?: string;
  flagged?: boolean;
  entity_id?: string;
  entity_name?: string;
  computed?: Record<string, unknown>;
  // FLW-level fields
  total_visits?: number;
  approved_visits?: number;
  pending_visits?: number;
  rejected_visits?: number;
  flagged_visits?: number;
  first_visit_date?: string;
  last_visit_date?: string;
  custom_fields?: Record<string, unknown>;
}

interface SQLPreview {
  terminal_stage: string;
  visit_extraction_sql: string;
  flw_aggregation_sql?: string;
  field_expressions: Record<string, FieldExpression>;
  histogram_expressions?: Record<string, unknown>;
  computed_fields?: string[];
}

interface FieldExpression {
  paths: string[];
  extraction_sql: string;
  transformed_sql: string;
  aggregation: string;
}

interface PipelineDataFromDjango {
  definition_id: number;
  opportunity_id: number;
  definition: PipelineDefinition;
  schema: PipelineSchema;
  render_code: string;
  stream_url: string;
  sql_preview_url: string;
}

// Props for dynamic pipeline component
interface PipelineProps {
  data: PipelineData | null;
  definition: PipelineDefinition;
  onRefresh: () => void;
}

// Declare Babel global
declare global {
  interface Window {
    Babel: {
      transform: (
        code: string,
        options: { presets: string[] },
      ) => { code: string };
    };
  }
}

// Load Babel standalone
function useBabelLoader(): boolean {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (window.Babel) {
      setLoaded(true);
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@babel/standalone@7.23.5/babel.min.js';
    script.async = true;
    script.onload = () => setLoaded(true);
    script.onerror = () => console.error('Failed to load Babel');
    document.head.appendChild(script);

    return () => {
      // Don't remove - might be used elsewhere
    };
  }, []);

  return loaded;
}

// Transpile and create component from JSX code
function createComponentFromCode(code: string): React.FC<PipelineProps> | null {
  if (!window.Babel) {
    console.error('DynamicPipeline: Babel not loaded yet');
    return null;
  }

  try {
    const wrappedCode = `
      (function(React) {
        ${code}
        return typeof PipelineUI !== 'undefined' ? PipelineUI : null;
      })
    `;

    const transformed = window.Babel.transform(wrappedCode, {
      presets: ['react'],
    });

    const factory = eval(transformed.code);
    const Component = factory(React);

    if (!Component) {
      console.error('DynamicPipeline: PipelineUI component not found');
      return null;
    }

    return Component;
  } catch (error) {
    console.error(
      'DynamicPipeline: Failed to transpile/create component:',
      error,
    );
    return null;
  }
}

// Error boundary
class ErrorBoundary extends React.Component<
  { children: React.ReactNode; onError?: (error: string) => void },
  { hasError: boolean; error: string | null }
> {
  constructor(props: {
    children: React.ReactNode;
    onError?: (error: string) => void;
  }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error.message);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <h3 className="text-lg font-semibold text-red-800">
            Error rendering pipeline
          </h3>
          <p className="text-red-600 text-sm font-mono">{this.state.error}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

// Dynamic pipeline component
function DynamicPipeline({
  renderCode,
  data,
  definition,
  onRefresh,
  onError,
}: {
  renderCode: string;
  data: PipelineData | null;
  definition: PipelineDefinition;
  onRefresh: () => void;
  onError?: (error: string) => void;
}) {
  const babelLoaded = useBabelLoader();

  const DynamicComponent = useMemo(() => {
    if (!babelLoaded || !renderCode) return null;
    return createComponentFromCode(renderCode);
  }, [babelLoaded, renderCode]);

  if (!babelLoaded) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2 text-gray-600">Loading renderer...</span>
      </div>
    );
  }

  if (!DynamicComponent) {
    return (
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <p className="text-yellow-800">
          No render code available. Use the AI chat to create a visualization.
        </p>
      </div>
    );
  }

  return (
    <ErrorBoundary onError={onError}>
      <DynamicComponent
        data={data}
        definition={definition}
        onRefresh={onRefresh}
      />
    </ErrorBoundary>
  );
}

// SQL Preview Panel
function SQLPreviewPanel({
  sqlPreview,
  isLoading,
  onRefresh,
}: {
  sqlPreview: SQLPreview | null;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  if (!sqlPreview && !isLoading) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-gray-600" />
          <span className="font-medium text-gray-900">SQL Preview</span>
          {sqlPreview && (
            <span className="text-sm text-gray-500">
              ({sqlPreview.terminal_stage})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRefresh();
            }}
            className="p-1 hover:bg-gray-100 rounded"
            title="Refresh SQL preview"
          >
            <RefreshCw
              className={`w-4 h-4 text-gray-500 ${
                isLoading ? 'animate-spin' : ''
              }`}
            />
          </button>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-gray-200 p-4 space-y-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              <span className="ml-2 text-gray-600">Loading SQL preview...</span>
            </div>
          ) : sqlPreview ? (
            <>
              {/* Visit Extraction SQL */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold text-gray-700">
                    Visit Extraction Query
                  </h4>
                  <button
                    onClick={() =>
                      copyToClipboard(sqlPreview.visit_extraction_sql, 'visit')
                    }
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded"
                  >
                    {copiedField === 'visit' ? (
                      <Check className="w-3 h-3 text-green-600" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                    Copy
                  </button>
                </div>
                <pre className="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto">
                  {sqlPreview.visit_extraction_sql}
                </pre>
              </div>

              {/* FLW Aggregation SQL (if aggregated) */}
              {sqlPreview.flw_aggregation_sql && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-semibold text-gray-700">
                      FLW Aggregation Query
                    </h4>
                    <button
                      onClick={() =>
                        copyToClipboard(sqlPreview.flw_aggregation_sql!, 'flw')
                      }
                      className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded"
                    >
                      {copiedField === 'flw' ? (
                        <Check className="w-3 h-3 text-green-600" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                      Copy
                    </button>
                  </div>
                  <pre className="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto">
                    {sqlPreview.flw_aggregation_sql}
                  </pre>
                </div>
              )}

              {/* Field Expressions */}
              {Object.keys(sqlPreview.field_expressions).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">
                    Field Expressions
                  </h4>
                  <div className="space-y-2">
                    {Object.entries(sqlPreview.field_expressions).map(
                      ([name, expr]) => (
                        <div
                          key={name}
                          className="bg-gray-50 p-2 rounded text-xs"
                        >
                          <div className="font-medium text-gray-800">
                            {name}
                          </div>
                          <div className="text-gray-600 mt-1">
                            <span className="text-gray-500">Paths:</span>{' '}
                            {expr.paths.join(', ')}
                          </div>
                          <div className="text-gray-600">
                            <span className="text-gray-500">SQL:</span>{' '}
                            <code className="bg-gray-200 px-1 rounded">
                              {expr.transformed_sql}
                            </code>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-gray-500 text-sm">No SQL preview available</p>
          )}
        </div>
      )}
    </div>
  );
}

// Pipeline Chat Component (simplified version of WorkflowChat)
function PipelineChat({
  definition,
  definitionId,
  opportunityId,
  schema,
  renderCode,
  onSchemaUpdate,
  onRenderCodeUpdate,
  onClose,
}: {
  definition: PipelineDefinition;
  definitionId: number;
  opportunityId: number;
  schema: PipelineSchema;
  renderCode: string;
  onSchemaUpdate: (newSchema: PipelineSchema) => void;
  onRenderCodeUpdate: (newRenderCode: string) => void;
  onClose?: () => void;
}) {
  const [messages, setMessages] = useState<
    Array<{ role: string; content: string }>
  >([]);
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [modelProvider, setModelProvider] = useState<'anthropic' | 'openai'>(
    'anthropic',
  );
  const [showSettings, setShowSettings] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load chat history on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await fetch(
          `/labs/pipelines/api/${definitionId}/chat/history/?opportunity_id=${opportunityId}`,
        );
        const data = await response.json();
        if (data.messages) {
          setMessages(data.messages);
        }
      } catch (e) {
        console.error('Failed to load chat history:', e);
      }
    };
    loadHistory();
  }, [definitionId, opportunityId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSubmitting) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setIsSubmitting(true);

    try {
      // Get CSRF token
      const csrfToken =
        document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')
          ?.value || '';

      // Prepare context with current pipeline state
      const currentCode = JSON.stringify({
        definition: schema,
        render_code: renderCode,
        model_provider: modelProvider,
        definition_id: definitionId,
        opportunity_id: opportunityId,
      });

      // Use FormData like WorkflowChat - Django expects form data, not JSON
      const formData = new FormData();
      formData.append('prompt', userMessage);
      formData.append('agent', 'pipeline');
      formData.append('current_code', currentCode);

      // Submit to AI endpoint
      const response = await fetch('/ai/demo/submit/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
        body: formData,
      });

      const { task_id } = await response.json();

      // Poll for result
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await fetch(
            `/ai/demo/status/?task_id=${task_id}&opportunity_id=${opportunityId}`,
          );
          const data = await statusResponse.json();

          if (data.status === 'SUCCESS') {
            clearInterval(pollInterval);

            const assistantMessage: {
              role: string;
              content: string;
              schemaChanged?: boolean;
              renderCodeChanged?: boolean;
            } = {
              role: 'assistant',
              content: data.result.message || 'Changes applied.',
            };

            // Handle schema update
            if (data.result.schema_changed && data.result.schema) {
              assistantMessage.schemaChanged = true;
              onSchemaUpdate(data.result.schema);
            }

            // Handle render code update
            if (data.result.render_code_changed && data.result.render_code) {
              assistantMessage.renderCodeChanged = true;
              onRenderCodeUpdate(data.result.render_code);
            }

            setMessages((prev) => [...prev, assistantMessage]);
            setIsSubmitting(false);
          } else if (data.status === 'FAILURE') {
            clearInterval(pollInterval);
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content: `Error: ${data.error || 'Unknown error'}`,
              },
            ]);
            setIsSubmitting(false);
          }
        } catch (e) {
          console.error('Error polling task status:', e);
        }
      }, 1000);
    } catch (e) {
      console.error('Failed to submit message:', e);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Failed to send message. Please try again.',
        },
      ]);
      setIsSubmitting(false);
    }
  };

  const handleClearHistory = async () => {
    try {
      const csrfToken =
        document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')
          ?.value || '';
      await fetch(`/labs/pipelines/api/${definitionId}/chat/clear/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      setMessages([]);
    } catch (e) {
      console.error('Failed to clear history:', e);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <h3 className="font-semibold text-gray-900">Pipeline AI Assistant</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 hover:bg-gray-100 rounded"
            title="Settings"
          >
            <Code className="w-4 h-4 text-gray-600" />
          </button>
          {onClose && (
            <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded">
              <X className="w-4 h-4 text-gray-600" />
            </button>
          )}
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="p-4 bg-gray-50 border-b space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Model
            </label>
            <select
              value={modelProvider}
              onChange={(e) =>
                setModelProvider(e.target.value as 'anthropic' | 'openai')
              }
              className="w-full p-2 border rounded"
            >
              <option value="anthropic">Claude (Anthropic)</option>
              <option value="openai">GPT-4 (OpenAI)</option>
            </select>
          </div>
          <button
            onClick={handleClearHistory}
            className="text-sm text-red-600 hover:text-red-800"
          >
            Clear chat history
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            <p className="mb-2">Ask me to help with your pipeline!</p>
            <p className="text-sm">
              Examples: "Add a weight field", "Show a chart", "Filter by
              approved visits"
            </p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${
              msg.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[85%] rounded-lg p-3 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {isSubmitting && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <div className="animate-pulse flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animation-delay-200"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animation-delay-400"></div>
                </div>
                <span className="text-gray-500 text-sm">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your pipeline..."
            disabled={isSubmitting}
            className="flex-1 p-2 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={isSubmitting || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

// Main Pipeline Runner Component
function PipelineRunner({
  initialData,
}: {
  initialData: PipelineDataFromDjango;
}) {
  const [schema, setSchema] = useState<PipelineSchema>(initialData.schema);
  const [renderCode, setRenderCode] = useState(initialData.render_code || '');
  const [pipelineData, setPipelineData] = useState<PipelineData | null>(null);
  const [sqlPreview, setSqlPreview] = useState<SQLPreview | null>(null);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [isLoadingSql, setIsLoadingSql] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCodeEditorOpen, setIsCodeEditorOpen] = useState(false);
  const [editedCode, setEditedCode] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Track changes
  const originalSchema = initialData.schema;
  const originalRenderCode = initialData.render_code || '';

  const hasChanges = useMemo(() => {
    const schemaChanged =
      JSON.stringify(schema) !== JSON.stringify(originalSchema);
    const codeChanged = renderCode !== originalRenderCode;
    return schemaChanged || codeChanged;
  }, [schema, renderCode, originalSchema, originalRenderCode]);

  // Load data via SSE
  const loadData = useCallback(() => {
    setIsLoadingData(true);
    setError(null);
    setLoadingMessage('Connecting...');

    const eventSource = new EventSource(
      `${initialData.stream_url}?opportunity_id=${initialData.opportunity_id}`,
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.error) {
          setError(data.error);
          setIsLoadingData(false);
          eventSource.close();
          return;
        }

        // SSE events have: { message, complete, data?, error? }
        if (data.complete && data.data) {
          setPipelineData(data.data);
          setIsLoadingData(false);
          eventSource.close();
        } else {
          setLoadingMessage(data.message || 'Loading...');
        }
      } catch (e) {
        console.error('Failed to parse SSE event:', e);
      }
    };

    eventSource.onerror = () => {
      setError('Connection lost. Please refresh.');
      setIsLoadingData(false);
      eventSource.close();
    };
  }, [initialData.stream_url, initialData.opportunity_id]);

  // Load SQL preview
  const loadSqlPreview = useCallback(async () => {
    setIsLoadingSql(true);
    try {
      const response = await fetch(
        `${initialData.sql_preview_url}?opportunity_id=${initialData.opportunity_id}`,
      );
      const data = await response.json();
      setSqlPreview(data);
    } catch (e) {
      console.error('Failed to load SQL preview:', e);
    }
    setIsLoadingSql(false);
  }, [initialData.sql_preview_url, initialData.opportunity_id]);

  // Initial load
  useEffect(() => {
    loadData();
    loadSqlPreview();
  }, [loadData, loadSqlPreview]);

  // Handle schema update from AI
  const handleSchemaUpdate = useCallback(
    (newSchema: PipelineSchema) => {
      setSchema(newSchema);
      // Reload SQL preview when schema changes
      loadSqlPreview();
    },
    [loadSqlPreview],
  );

  // Handle render code update from AI
  const handleRenderCodeUpdate = useCallback((newRenderCode: string) => {
    setRenderCode(newRenderCode);
  }, []);

  // Save changes
  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setError(null);

    const csrfToken =
      document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')
        ?.value || '';

    try {
      // Save schema if changed
      if (JSON.stringify(schema) !== JSON.stringify(originalSchema)) {
        const schemaResponse = await fetch(
          `/labs/pipelines/api/${initialData.definition_id}/save/`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ schema }),
          },
        );

        if (!schemaResponse.ok) {
          throw new Error('Failed to save schema');
        }
      }

      // Save render code if changed
      if (renderCode !== originalRenderCode) {
        const codeResponse = await fetch(
          `/labs/pipelines/api/${initialData.definition_id}/render-code/`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ component_code: renderCode }),
          },
        );

        if (!codeResponse.ok) {
          throw new Error('Failed to save render code');
        }
      }

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);

      // Reload page to get fresh data
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    }

    setIsSaving(false);
  }, [
    schema,
    renderCode,
    originalSchema,
    originalRenderCode,
    initialData.definition_id,
  ]);

  // Discard changes
  const handleDiscard = useCallback(() => {
    setSchema(originalSchema);
    setRenderCode(originalRenderCode);
  }, [originalSchema, originalRenderCode]);

  // Open code editor
  const openCodeEditor = useCallback(() => {
    setEditedCode(renderCode);
    setIsCodeEditorOpen(true);
  }, [renderCode]);

  // Save code from editor
  const saveCodeFromEditor = useCallback(() => {
    setRenderCode(editedCode);
    setIsCodeEditorOpen(false);
  }, [editedCode]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Bar */}
      <div className="bg-white border-b sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                {initialData.definition.name}
              </h1>
              <p className="text-sm text-gray-600">
                {initialData.definition.description}
              </p>
            </div>

            <div className="flex items-center gap-3">
              {hasChanges && (
                <>
                  <button
                    onClick={handleDiscard}
                    className="flex items-center gap-1 px-3 py-2 text-gray-700 hover:bg-gray-100 rounded"
                  >
                    <RotateCcw className="w-4 h-4" />
                    Discard
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="flex items-center gap-1 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-300"
                  >
                    {isSaving ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    ) : saveSuccess ? (
                      <Check className="w-4 h-4" />
                    ) : (
                      <Save className="w-4 h-4" />
                    )}
                    {saveSuccess ? 'Saved!' : 'Save'}
                  </button>
                </>
              )}

              <button
                onClick={openCodeEditor}
                className="flex items-center gap-1 px-3 py-2 text-gray-700 hover:bg-gray-100 rounded"
                title="Edit render code"
              >
                <Code className="w-4 h-4" />
                Code
              </button>

              <button
                onClick={() => setIsChatOpen(!isChatOpen)}
                className={`flex items-center gap-1 px-3 py-2 rounded ${
                  isChatOpen
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <MessageCircle className="w-4 h-4" />
                AI Chat
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {isLoadingData && (
          <div className="mb-6 p-6 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-center gap-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <div>
                <h3 className="font-semibold text-blue-900">
                  Loading Pipeline Data
                </h3>
                <p className="text-sm text-blue-800">{loadingMessage}</p>
              </div>
            </div>
          </div>
        )}

        {/* SQL Preview */}
        <div className="mb-6">
          <SQLPreviewPanel
            sqlPreview={sqlPreview}
            isLoading={isLoadingSql}
            onRefresh={loadSqlPreview}
          />
        </div>

        {/* Pipeline Visualization */}
        <DynamicPipeline
          renderCode={renderCode}
          data={pipelineData}
          definition={initialData.definition}
          onRefresh={loadData}
          onError={setError}
        />
      </div>

      {/* Chat Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-96 bg-white shadow-2xl z-40 transform transition-transform duration-300 ease-in-out ${
          isChatOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {isChatOpen && (
          <PipelineChat
            definition={initialData.definition}
            definitionId={initialData.definition_id}
            opportunityId={initialData.opportunity_id}
            schema={schema}
            renderCode={renderCode}
            onSchemaUpdate={handleSchemaUpdate}
            onRenderCodeUpdate={handleRenderCodeUpdate}
            onClose={() => setIsChatOpen(false)}
          />
        )}
      </div>

      {/* Code Editor Modal */}
      {isCodeEditorOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setIsCodeEditorOpen(false)}
          />
          <div className="absolute inset-4 bg-white rounded-lg shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="text-lg font-semibold">Edit Render Code</h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={saveCodeFromEditor}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Apply Changes
                </button>
                <button
                  onClick={() => setIsCodeEditorOpen(false)}
                  className="p-2 hover:bg-gray-100 rounded"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <textarea
                value={editedCode}
                onChange={(e) => setEditedCode(e.target.value)}
                className="w-full h-full p-4 font-mono text-sm resize-none focus:outline-none"
                spellCheck={false}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Mount the application
function mount() {
  const container = document.getElementById('pipeline-runner-root');
  if (!container) {
    console.error('Pipeline runner root element not found');
    return;
  }

  const dataElement = document.getElementById('pipeline-data');
  if (!dataElement?.textContent) {
    console.error('Pipeline data not found');
    return;
  }

  try {
    const initialData = JSON.parse(
      dataElement.textContent,
    ) as PipelineDataFromDjango;
    const root = createRoot(container);
    root.render(<PipelineRunner initialData={initialData} />);
  } catch (e) {
    console.error('Failed to parse pipeline data:', e);
  }
}

// Run on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount);
} else {
  mount();
}
