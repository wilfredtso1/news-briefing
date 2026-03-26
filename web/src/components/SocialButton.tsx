import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function SocialButton({
            icon
        }: {
            icon: React.ReactNode;
        }) {
            return (
                <a
                    className={"button_button__atjat button_buttonVariantSimple__hzQDj button_buttonSizeS__IYg0e"}
                    rel={"noopener"}
                    target={"_blank"}
                >
                    {icon}
                </a>
            );
        }
    

export default SocialButton
