export type Field = {
  key: string;
  label: string;
  placeholder: string | undefined;
  type: string;
  required: boolean;
  validate: (v: any) => string;
};