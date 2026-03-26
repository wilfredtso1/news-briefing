import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function ButtonLink({
            label,
            variant,
            rel,
            target
        }: {
            label: string;
            variant: "template" | "arrow";
            rel?: string;
            target?: string;
        }) {
            const baseClass =
                "button_button__atjat button_buttonVariantSecondary__cZi4H button_buttonSizeM__NexGD";
    
            const className =
                variant === "arrow"
                    ? `${baseClass} button_hasArrowRight__yXJHC`
                    : baseClass;
    
            if (variant === "template") {
                return (
                    <a
                        className={className}
                        rel={rel}
                        target={target}
                        style={{ textAlign: "center" }}
                    >
                        <span className={"templateViewCta_templatesButton__msl_u"}>
                            <span>
                                {label}
                            </span>
                        </span>
                    </a>
                );
            }
    
            return (
                <a className={className}>
                    {label}
                    <span className={"Arrow_arrow__oVjWc Arrow_arrowAfter__8m7lp"}>
                        →
                    </span>
                </a>
            );
        }
    

export default ButtonLink
