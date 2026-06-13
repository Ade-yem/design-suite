import React, { useState } from "react";
import { Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Definition of a single questionnaire field passed from the backend.
 */
interface QuestionnaireField {
  path: string;
  domain: string;
  label: string;
  type: "number" | "boolean" | "select" | "text";
  options?: Array<string | number>;
  default?: any;
  description: string;
}

/**
 * Props definition for the QuestionnaireForm component.
 */
interface QuestionnaireFormProps {
  /** Title of questionaire */
  title: string;
  /** Description of questionaire */
  description: string;
  /** The list of fields to render in the form. */
  fields: QuestionnaireField[];
  /** Callback triggered when the form is validated and submitted. */
  onSubmit: (formattedResponse: string) => void;
  /** Optional class name to style the container. */
  className?: string;
}

/**
 * Dynamic QuestionnaireForm component.
 * Parses dynamic schemas sent by the backend Analyst Agent, groups inputs by domain,
 * provides client-side validation, and serializes output into a human-readable list.
 *
 * @param {QuestionnaireFormProps} props - Component properties.
 * @returns {React.JSX.Element} The rendered React component.
 */
export function QuestionnaireForm({ title, description, fields, onSubmit, className }: QuestionnaireFormProps): React.JSX.Element {
  // Initialize form state with backend defaults or sensible fallbacks
  const [formData, setFormData] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    fields.forEach((f) => {
      initial[f.path] = f.default !== undefined ? f.default : f.type === "boolean" ? false : "";
    });
    return initial;
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  // Group fields by their domain category
  const domains = Array.from(new Set(fields.map((f) => f.domain)));

  /**
   * Handle field change and clear active validation errors.
   */
  const handleChange = (path: string, value: any) => {
    setFormData((prev) => ({ ...prev, [path]: value }));
    if (errors[path]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[path];
        return next;
      });
    }
  };

  /**
   * Perform client-side validation on field inputs.
   */
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    fields.forEach((f) => {
      const val = formData[f.path];

      if (f.type === "number") {
        if (val === "" || val === null || val === undefined) {
          newErrors[f.path] = "Value is required";
        } else {
          const num = Number(val);
          if (isNaN(num)) {
            newErrors[f.path] = "Must be a valid number";
          } else if (num < 0) {
            newErrors[f.path] = "Value cannot be negative";
          }
        }
      } else if (f.type === "text" || f.type === "select") {
        if (!val || String(val).trim() === "") {
          newErrors[f.path] = "Selection / input is required";
        }
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  /**
   * Form submission handler. Serializes values into text format.
   */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setSubmitting(true);

    // Format the response text as a structured list
    const lines = ["Design considerations:"];
    fields.forEach((f) => {
      const val = formData[f.path];
      let formattedVal = val;
      if (f.type === "boolean") {
        formattedVal = val ? "Yes" : "No";
      }
      lines.push(`- ${f.label}: ${formattedVal}`);
    });

    const responseText = lines.join("\n");
    onSubmit(responseText);
  };

  if (!fields || fields.length === 0) {
    return (
      <div className="p-3 text-center text-xs text-muted-foreground border border-dashed border-border rounded-lg">
        No active questions required.
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "rounded-lg border border-primary/20 bg-card/60 p-4 space-y-4 shadow-sm animate-fade-in-up",
        className
      )}
    >
      <div className="border-b border-border/40 pb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-primary">
          {title}
        </h4>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          {description}
        </p>
      </div>

      <div className="space-y-4 max-h-[400px] overflow-y-auto pr-1">
        {domains.map((domain) => {
          const domainFields = fields.filter((f) => f.domain === domain);
          return (
            <div key={domain} className="space-y-2.5">
              <h5 className="text-[11px] font-bold text-foreground/75 border-l-2 border-primary/60 pl-1.5 uppercase">
                {domain}
              </h5>

              <div className="space-y-3 pl-2">
                {domainFields.map((field) => {
                  const error = errors[field.path];
                  const hasError = !!error;

                  return (
                    <div key={field.path} className="space-y-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <label className="text-xs font-medium text-foreground">
                          {field.label}
                        </label>
                        {hasError && (
                          <span className="text-[10px] text-destructive flex items-center gap-0.5">
                            <AlertCircle className="h-3 w-3" />
                            {error}
                          </span>
                        )}
                      </div>

                      {field.type === "boolean" ? (
                        <div className="flex items-center gap-2.5 py-1">
                          <button
                            type="button"
                            onClick={() => handleChange(field.path, !formData[field.path])}
                            className={cn(
                              "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-1 focus:ring-primary focus:ring-offset-1",
                              formData[field.path] ? "bg-primary" : "bg-muted"
                            )}
                          >
                            <span
                              className={cn(
                                "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition duration-200 ease-in-out",
                                formData[field.path] ? "translate-x-4" : "translate-x-0"
                              )}
                            />
                          </button>
                          <span className="text-xs text-muted-foreground">
                            {formData[field.path] ? "Yes" : "No"}
                          </span>
                        </div>
                      ) : field.type === "select" && field.options ? (
                        <select
                          value={formData[field.path]}
                          onChange={(e) => handleChange(field.path, e.target.value)}
                          className={cn(
                            "w-full h-8 px-2 rounded-md bg-muted/60 border border-border text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all",
                            hasError && "border-destructive/80 focus:ring-destructive focus:border-destructive"
                          )}
                        >
                          {field.options.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={field.type === "number" ? "number" : "text"}
                          step="any"
                          value={formData[field.path]}
                          onChange={(e) =>
                            handleChange(
                              field.path,
                              field.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value
                            )
                          }
                          placeholder={field.description}
                          className={cn(
                            "w-full h-8 px-2 rounded-md bg-muted/60 border border-border text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all",
                            hasError && "border-destructive/80 focus:ring-destructive focus:border-destructive"
                          )}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <button
        type="submit"
        disabled={submitting}
        className={cn(
          "w-full h-9 mt-2 rounded-md bg-primary hover:bg-primary/95 text-primary-foreground font-medium text-xs flex items-center justify-center gap-1.5 shadow-sm transition-all active:scale-[0.98]",
          submitting && "opacity-70 cursor-not-allowed"
        )}
      >
        <Check className="h-3.5 w-3.5" />
        {submitting ? "Submitting Parameters..." : "Submit Project Brief"}
      </button>
    </form>
  );
}
